"""TX State Senate collector.

senate.texas.gov publishes a single non-paginated HTML pressroom page
per district at pressroom.php?d=N. Each year is a <h3>YEAR</h3>
header followed by sibling <p> blocks. Each <p> carries:

  - leading text "MM/DD/YYYY"
  - an <img> icon (pdficon_sm.png for PDFs, playbutton_sm.png for video)
  - an <a> with the title and the PDF or videoplayer.php URL

No JS, no Akamai, no pagination. One fetch per senator. PDF bodies are
linked but not fetched here — body extraction is a separate enrichment
step.

Two Texas-specific quirks drive the collection window and the redirect
check below; see PROJECT_WINDOW_START and _is_vacancy_redirect.
"""

import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from pipeline.collectors.base import CollectorResult, ReleaseRecord, HealthCheckResult
from pipeline.lib.http import create_client, fetch_with_retry
from pipeline.lib.identity import normalize_url

log = logging.getLogger("capitol.collector.tx_senate")

DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
BASE_URL = "https://senate.texas.gov/"

# Texas Senate offices upload press PDFs in backdated batches: the listing
# date is the release date, not the upload date, and the two can be months
# apart. Verified 2026-07-25 against Last-Modified on the PDFs themselves —
# d13's 01/08/2026 and 02/17/2026 items were both uploaded 2026-05-13, and
# d24's 03/18/2026 item landed 2026-07-01.
#
# The daily updater passes `since` = "when the last run finished" (hours
# ago), so every backdated batch fell outside the window and was dropped
# permanently. That is why 12 districts sat at zero records while their
# pressrooms carried live 2026 content.
#
# Fix: ignore a narrow incremental `since` and re-sweep the whole project
# window on every run, letting update.py dedup on source_url. One fetch per
# member and roughly 350 in-window items chamber-wide, so the re-sweep is
# cheap. An explicitly earlier `since` (deep backfill) is still honored.
PROJECT_WINDOW_START = datetime(2025, 1, 1, tzinfo=timezone.utc)

# senate.texas.gov 302s pressroom.php?d=N to the chamber roster when N has no
# sitting member. Following that redirect yields HTTP 200 with zero items,
# which is indistinguishable from a quiet pressroom unless we check the URL.
VACANCY_REDIRECT_PATH = "members.php"


class TxSenateCollector:
    """Collects TX state senate press releases.

    Listings include both PDF press releases and videoplayer.php video
    items. We collect both; videos are classified as `other` since the
    body lives off-platform.
    """

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        start = time.monotonic()
        sid = senator["official_id"]
        pr_url = senator.get("press_release_url", "")
        result = CollectorResult(official_id=sid, method="tx_senate")

        if not pr_url:
            result.errors.append("No press_release_url configured")
            return result

        async with create_client() as client:
            try:
                resp = await fetch_with_retry(client, pr_url)
            except Exception as e:
                result.errors.append(f"Fetch failed: {type(e).__name__}: {e}")
                return result

            if resp.status_code != 200:
                result.errors.append(f"HTTP {resp.status_code}")
                return result

            if _is_vacancy_redirect(pr_url, resp):
                result.errors.append(
                    "Pressroom redirected to the chamber roster; the district "
                    "has no sitting member"
                )
                return result

            result.pages_scraped = 1
            soup = BeautifulSoup(resp.text, "lxml")
            items = _extract_items(soup, pr_url)

            if not items and not _expect_empty(senator):
                result.errors.append("No items found")
                return result

            cutoff = _effective_since(since)
            for item in items:
                # Texas listings expose dates, not times. Compare on day
                # boundaries so a release posted later today is not skipped
                # just because its parsed timestamp is midnight UTC.
                if item["published_at"] and item["published_at"].date() < cutoff.date():
                    continue
                # Bump last_seen_live for everything in the window, including
                # rows the updater will dedup away. Without this the freshness
                # signal freezes at the day a member's last new item landed
                # and a healthy-but-quiet pressroom reads as a dead collector.
                result.seen_urls.add(item["source_url"])
                rec = ReleaseRecord(
                    official_id=sid,
                    title=item["title"],
                    source_url=item["source_url"],
                    published_at=item["published_at"],
                    body_text="",
                    raw_html=item["raw_html"],
                    content_type=item["content_type"],
                    date_source=item["date_source"],
                    date_confidence=item["date_confidence"],
                    # Body extraction is a later enrichment step. Leave this
                    # empty so the updater does not compare a listing hash
                    # against a body hash and blank an extracted body.
                    content_hash="",
                )
                result.releases.append(rec)

        result.duration_seconds = time.monotonic() - start
        log.info(
            "tx_senate collected %d items for %s (%.1fs)",
            len(result.releases), sid, result.duration_seconds,
        )
        return result

    async def health_check(self, senator: dict) -> HealthCheckResult:
        sid = senator["official_id"]
        pr_url = senator.get("press_release_url", "")
        result = HealthCheckResult(official_id=sid)

        if not pr_url:
            result.error_message = "No press_release_url"
            return result

        start = time.monotonic()
        try:
            async with create_client() as client:
                resp = await fetch_with_retry(client, pr_url)
        except Exception as e:
            result.error_message = f"{type(e).__name__}: {e}"
            return result

        result.url_status = resp.status_code
        result.page_load_ms = int((time.monotonic() - start) * 1000)
        if resp.status_code != 200:
            return result

        if _is_vacancy_redirect(pr_url, resp):
            result.error_message = (
                "Pressroom redirected to the chamber roster; the district has "
                "no sitting member"
            )
            return result

        soup = BeautifulSoup(resp.text, "lxml")
        items = _extract_items(soup, pr_url)
        result.items_found = len(items)
        result.allow_empty = _expect_empty(senator)
        result.selector_ok = bool(items) or result.allow_empty
        result.date_parseable = any(it["published_at"] for it in items)
        return result


def _effective_since(since: datetime | None) -> datetime:
    """Widen a narrow incremental cutoff to the full project window.

    Honors a caller that explicitly asks for something earlier (deep
    backfill) but never lets the daily "since last run" value shrink the
    sweep, because Texas backdates its uploads. See PROJECT_WINDOW_START.
    """
    if since and since < PROJECT_WINDOW_START:
        return since
    return PROJECT_WINDOW_START


def _is_vacancy_redirect(requested_url: str, resp) -> bool:
    """True when a pressroom request landed on the chamber roster instead."""
    final = str(resp.url)
    return VACANCY_REDIRECT_PATH in final and VACANCY_REDIRECT_PATH not in requested_url


def _extract_items(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Walk year-grouped <p> items off <h3> headers, return list of dicts.

    Container varies across senators (some use div.prlist, some put items
    directly under .content). Walk the whole document in document order;
    the h3 year + sibling <p> shape is consistent.
    """
    items: list[dict] = []

    current_year: int | None = None
    for el in soup.find_all(["h3", "p"]):
        if el.name == "h3":
            txt = el.get_text(strip=True)
            m = re.match(r"(\d{4})", txt)
            if m:
                current_year = int(m.group(1))
            continue

        if el.name != "p":
            continue

        a = el.find("a", href=True)
        if not a:
            continue

        title = a.get_text(" ", strip=True)
        if not title:
            continue

        href = a["href"]
        # skip non-content links (back-to-top, mailto, etc.)
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue

        full_url = urljoin(base_url, href)
        full_url = normalize_url(full_url)

        # restrict to actual press content paths
        url_lower = full_url.lower()
        # Site-wide assets (floor charts, forms) live under /_assets/ and are
        # PDFs too. They are chrome, not member output.
        if "/_assets/" in url_lower:
            continue
        is_pdf = url_lower.endswith(".pdf") or "/press/" in url_lower
        is_video = "videoplayer.php" in url_lower
        is_press_html = "press.php" in url_lower
        if not (is_pdf or is_video or is_press_html):
            continue

        text = el.get_text(" ", strip=True)
        date_m = DATE_RE.search(text)
        published_at = None
        date_source = ""
        date_confidence = 0.0
        if date_m:
            mm, dd, yyyy = date_m.groups()
            try:
                published_at = datetime(int(yyyy), int(mm), int(dd), tzinfo=timezone.utc)
                date_source = "listing_text"
                date_confidence = 1.0
            except ValueError:
                published_at = None

        if published_at is None and current_year:
            # Fall back to the year header as Jan 1. The year is real but the
            # day is a guess, so label it as such rather than inheriting the
            # full confidence an explicit MM/DD/YYYY row earns.
            try:
                published_at = datetime(current_year, 1, 1, tzinfo=timezone.utc)
                date_source = "listing_year_header"
                date_confidence = 0.4
            except ValueError:
                pass

        content_type = "other" if is_video else "press_release"
        if is_video and not title.upper().startswith("VIDEO"):
            title = f"VIDEO: {title}"
        if is_video and published_at:
            # Texas occasionally reuses the same videoplayer.php URL for
            # multiple dated pressroom rows. source_url is the natural DB key,
            # so include listing_date for video rows to preserve each listing.
            sep = "&" if "?" in full_url else "?"
            full_url = normalize_url(f"{full_url}{sep}listing_date={published_at:%Y%m%d}")

        items.append({
            "title": title,
            "source_url": full_url,
            "published_at": published_at,
            "content_type": content_type,
            "date_source": date_source,
            "date_confidence": date_confidence,
            "raw_html": str(el),
        })

    return items


def _expect_empty(senator: dict) -> bool:
    """Return true when a configured pressroom is expected to have no items."""
    return bool(
        senator.get("expect_empty")
        or (senator.get("scrape_config") or {}).get("expect_empty")
    )
