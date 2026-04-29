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
"""

import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from pipeline.collectors.base import CollectorResult, ReleaseRecord, HealthCheckResult
from pipeline.lib.http import create_client, fetch_with_retry
from pipeline.lib.identity import normalize_url, content_hash

log = logging.getLogger("capitol.collector.tx_senate")

DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
BASE_URL = "https://senate.texas.gov/"


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
        sid = senator["senator_id"]
        pr_url = senator.get("press_release_url", "")
        result = CollectorResult(senator_id=sid, method="tx_senate")

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

            result.pages_scraped = 1
            soup = BeautifulSoup(resp.text, "lxml")
            items = _extract_items(soup, pr_url)

            if not items and not senator.get("scrape_config", {}).get("expect_empty"):
                result.errors.append("No items found")
                return result

            for item in items:
                if since and item["published_at"] and item["published_at"] < since:
                    continue
                rec = ReleaseRecord(
                    senator_id=sid,
                    title=item["title"],
                    source_url=item["source_url"],
                    published_at=item["published_at"],
                    body_text="",
                    raw_html=item["raw_html"],
                    content_type=item["content_type"],
                    date_source="listing_text",
                    date_confidence=1.0 if item["published_at"] else 0.0,
                    content_hash=content_hash(f"{item['title']}|{item['source_url']}"),
                )
                result.releases.append(rec)

        result.duration_seconds = time.monotonic() - start
        log.info(
            "tx_senate collected %d items for %s (%.1fs)",
            len(result.releases), sid, result.duration_seconds,
        )
        return result

    async def health_check(self, senator: dict) -> HealthCheckResult:
        sid = senator["senator_id"]
        pr_url = senator.get("press_release_url", "")
        result = HealthCheckResult(senator_id=sid)

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

        soup = BeautifulSoup(resp.text, "lxml")
        items = _extract_items(soup, pr_url)
        result.items_found = len(items)
        result.selector_ok = bool(items) or bool(senator.get("scrape_config", {}).get("expect_empty"))
        result.date_parseable = any(it["published_at"] for it in items)
        return result


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
        is_pdf = url_lower.endswith(".pdf") or "/press/" in url_lower
        is_video = "videoplayer.php" in url_lower
        is_press_html = "press.php" in url_lower
        if not (is_pdf or is_video or is_press_html):
            continue

        text = el.get_text(" ", strip=True)
        date_m = DATE_RE.search(text)
        published_at = None
        if date_m:
            mm, dd, yyyy = date_m.groups()
            try:
                published_at = datetime(int(yyyy), int(mm), int(dd), tzinfo=timezone.utc)
            except ValueError:
                published_at = None

        if published_at is None and current_year:
            # fall back to year header as Jan 1 of that year, low confidence
            try:
                published_at = datetime(current_year, 1, 1, tzinfo=timezone.utc)
            except ValueError:
                pass

        content_type = "other" if is_video else "press_release"
        if is_video and not title.upper().startswith("VIDEO"):
            title = f"VIDEO: {title}"

        items.append({
            "title": title,
            "source_url": full_url,
            "published_at": published_at,
            "content_type": content_type,
            "raw_html": str(el),
        })

    return items
