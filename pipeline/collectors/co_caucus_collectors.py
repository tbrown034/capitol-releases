"""Colorado legislative caucus collectors.

Colorado is the first jurisdiction where the per-member pressroom model
does not apply at all. Verified 2026-07-25 against leg.colorado.gov: none
of the 100 legislators publishes press output on a .gov page, and
leg.colorado.gov/news and /press-releases both 404. One hundred percent of
Colorado legislative press output comes from the four party caucus
organizations, on three different commercial CMS platforms.

So the collected record's author is the CAUCUS, not a legislator. Records
land against a `caucus_pressroom` official row. Per-legislator attribution
is a separate, many-to-many pass -- see pipeline/lib/co_attribution.py --
because the recon measured a mean of 3.2 sitting legislators named per
release and only 10.5% naming any legislator in the title. Picking one
"author" per release would misattribute roughly nine in ten.

Three source families, one collector each:

  co_caucus_squarespace  senatedems.co + coloradohouserepublicans.com
  co_caucus_wp           coloradosenaterepublicans.com (WP-JSON)
  co_caucus_wix          cohousedems.com (sitemap walk, no feed)

None of these calls classifier.is_external_content(); that helper allowlists
senate.gov / house.gov / whitehouse.gov and would silently drop every
Colorado URL, which lives on .com and .co domains.
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from pipeline.collectors.base import CollectorResult, HealthCheckResult, ReleaseRecord
from pipeline.lib.dates import is_plausible_date, parse_date_text
from pipeline.lib.http import create_client, fetch_with_retry, politeness_delay
from pipeline.lib.identity import content_hash, normalize_url

log = logging.getLogger("capitol.collector.co_caucus")


# Squarespace and WordPress both hand us an authoritative publication
# timestamp straight from the CMS, so those dates are not parsed out of
# prose and carry full confidence. The Wix sitemap walk has to read a date
# string out of the rendered page, which is weaker on both counts.
_CMS_DATE_CONFIDENCE = 1.0
_DETAIL_TEXT_DATE_CONFIDENCE = 0.8
_SITEMAP_LASTMOD_CONFIDENCE = 0.4

_MONTH_DAY_YEAR_PAT = re.compile(
    r"\b((?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4})\b",
    re.IGNORECASE,
)


def _html_to_text(html: str) -> str:
    """Flatten a CMS-supplied HTML body fragment to readable text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for junk in soup.select("script, style, nav, form, noscript"):
        junk.decompose()
    return soup.get_text("\n", strip=True)


def _classify(title: str, default: str) -> str:
    """Refine the seed's per-source content_type from the headline.

    The seed maps a whole listing to one type (a caucus "newsroom" is
    press releases, an "op-eds" collection is op_eds). A release that
    announces itself as a statement in its own title is still a statement,
    so let the title override -- but only in that direction, never
    upgrading an op-ed source into a press release.
    """
    lowered = (title or "").lower()
    if default != "press_release":
        return default
    if "statement" in lowered:
        return "statement"
    if lowered.startswith(("op-ed", "oped", "opinion")) or "op-ed:" in lowered:
        return "op_ed"
    return default


def _within(since: datetime | None, published_at: datetime | None) -> bool:
    """True when a record is new enough to keep."""
    if since is None or published_at is None:
        return True
    return published_at.date() >= since.date()


def _sources(official: dict) -> list[dict]:
    config = official.get("scrape_config") or {}
    sources = config.get("sources") or []
    if sources:
        return sources
    pr_url = official.get("press_release_url")
    return [{"url": pr_url, "content_type": "press_release"}] if pr_url else []


class ColoradoCaucusSquarespaceCollector:
    """Collects Squarespace-hosted caucus newsrooms.

    Squarespace serves any collection URL as JSON with ?format=json. The
    response carries the newest 20 items with a millisecond `publishOn`
    and the full `body` HTML, so no detail fetch is needed. Walking back
    means re-requesting with &offset set to the last item's publishOn.
    """

    method = "co_caucus_squarespace"

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        start = time.monotonic()
        sid = senator["official_id"]
        result = CollectorResult(official_id=sid, method=self.method)
        sources = _sources(senator)

        if not sources:
            result.errors.append("No scrape_config.sources configured")
            return result

        async with create_client() as client:
            for source in sources:
                listing_url = source.get("url")
                if not listing_url:
                    continue
                default_type = source.get("content_type", "press_release")
                offset = None
                page = 0

                while page < max_pages:
                    page += 1
                    url = f"{listing_url}?format=json"
                    if offset is not None:
                        url = f"{url}&offset={offset}"

                    try:
                        resp = await fetch_with_retry(client, url)
                    except Exception as e:
                        result.errors.append(
                            f"{listing_url} page {page} fetch failed: {type(e).__name__}: {e}")
                        break

                    if resp.status_code != 200:
                        result.errors.append(
                            f"{listing_url} page {page} returned HTTP {resp.status_code}")
                        break

                    try:
                        payload = resp.json()
                    except (json.JSONDecodeError, ValueError) as e:
                        result.errors.append(f"{listing_url} page {page} not JSON: {e}")
                        break

                    items = payload.get("items") or []
                    if not items:
                        break

                    result.pages_scraped = max(result.pages_scraped, page)
                    oldest_on_page = None

                    for item in items:
                        publish_on = item.get("publishOn")
                        published_at = None
                        if publish_on:
                            published_at = datetime.fromtimestamp(
                                publish_on / 1000, tz=timezone.utc)
                            oldest_on_page = (
                                publish_on if oldest_on_page is None
                                else min(oldest_on_page, publish_on)
                            )

                        if not _within(since, published_at):
                            continue

                        title = (item.get("title") or "").strip()
                        full_url = item.get("fullUrl") or ""
                        source_url = urljoin(listing_url, full_url)
                        raw_html = item.get("body") or ""
                        body_text = _html_to_text(raw_html)

                        result.releases.append(ReleaseRecord(
                            official_id=sid,
                            title=title,
                            source_url=normalize_url(source_url),
                            published_at=published_at,
                            body_text=body_text,
                            raw_html=raw_html,
                            content_type=_classify(title, default_type),
                            date_source="cms_publish_field",
                            date_confidence=_CMS_DATE_CONFIDENCE if published_at else 0.0,
                            content_hash=content_hash(body_text or f"{title}|{source_url}"),
                        ))

                    if oldest_on_page is None:
                        break
                    # Squarespace pages strictly backwards, so once the whole
                    # page predates the cutoff there is nothing newer deeper in.
                    if since and datetime.fromtimestamp(
                            oldest_on_page / 1000, tz=timezone.utc).date() < since.date():
                        break
                    if offset == oldest_on_page:
                        break
                    offset = oldest_on_page
                    await politeness_delay(0.4)

        if not result.releases and not result.errors and not senator.get("expect_empty"):
            result.errors.append("No items found")

        result.duration_seconds = time.monotonic() - start
        log.info("%s collected %d items for %s (%d pages, %.1fs)",
                 self.method, len(result.releases), sid,
                 result.pages_scraped, result.duration_seconds)
        return result

    async def health_check(self, senator: dict) -> HealthCheckResult:
        return await _health_check_json(senator, self.method, _squarespace_probe)


class ColoradoCaucusWordPressCollector:
    """Collects the Colorado Senate Republicans WordPress caucus site.

    wp-json is open and unauthenticated. Category filtering is mandatory:
    the site-wide feed mixes original releases with "PRINT:" and "VIDEO:"
    clippings, which the original-content-only rule excludes. The seed
    names the allowed category ids per source.
    """

    method = "co_caucus_wp"
    per_page = 100

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        start = time.monotonic()
        sid = senator["official_id"]
        result = CollectorResult(official_id=sid, method=self.method)
        sources = _sources(senator)

        if not sources:
            result.errors.append("No scrape_config.sources configured")
            return result

        async with create_client() as client:
            for source in sources:
                endpoint = source.get("url")
                if not endpoint:
                    continue
                default_type = source.get("content_type", "press_release")
                joiner = "&" if "?" in endpoint else "?"

                for page in range(1, max_pages + 1):
                    url = f"{endpoint}{joiner}per_page={self.per_page}&page={page}"
                    try:
                        resp = await fetch_with_retry(client, url)
                    except Exception as e:
                        result.errors.append(
                            f"{endpoint} page {page} fetch failed: {type(e).__name__}: {e}")
                        break

                    # WP answers a page past the end with 400 rest_post_invalid_page_number.
                    if resp.status_code == 400 and page > 1:
                        break
                    if resp.status_code != 200:
                        result.errors.append(
                            f"{endpoint} page {page} returned HTTP {resp.status_code}")
                        break

                    try:
                        posts = resp.json()
                    except (json.JSONDecodeError, ValueError) as e:
                        result.errors.append(f"{endpoint} page {page} not JSON: {e}")
                        break

                    if not posts:
                        break

                    result.pages_scraped = max(result.pages_scraped, page)
                    stop = False

                    for post in posts:
                        published_at = _parse_wp_date(post.get("date_gmt") or post.get("date"))
                        if since and published_at and published_at.date() < since.date():
                            stop = True
                            continue

                        title = _html_to_text((post.get("title") or {}).get("rendered", ""))
                        raw_html = (post.get("content") or {}).get("rendered", "")
                        body_text = _html_to_text(raw_html)
                        source_url = post.get("link") or ""

                        result.releases.append(ReleaseRecord(
                            official_id=sid,
                            title=title,
                            source_url=normalize_url(source_url),
                            published_at=published_at,
                            body_text=body_text,
                            raw_html=raw_html,
                            content_type=_classify(title, default_type),
                            date_source="wp_json_date",
                            date_confidence=_CMS_DATE_CONFIDENCE if published_at else 0.0,
                            content_hash=content_hash(body_text or f"{title}|{source_url}"),
                        ))

                    # WP-JSON returns newest first, so a page that fell entirely
                    # past the cutoff means every later page has too.
                    if stop and not any(
                        p for p in posts
                        if (d := _parse_wp_date(p.get("date_gmt") or p.get("date")))
                        and since and d.date() >= since.date()
                    ):
                        break
                    if len(posts) < self.per_page:
                        break
                    await politeness_delay(0.4)

        if not result.releases and not result.errors and not senator.get("expect_empty"):
            result.errors.append("No items found")

        result.duration_seconds = time.monotonic() - start
        log.info("%s collected %d items for %s (%d pages, %.1fs)",
                 self.method, len(result.releases), sid,
                 result.pages_scraped, result.duration_seconds)
        return result

    async def health_check(self, senator: dict) -> HealthCheckResult:
        return await _health_check_json(senator, self.method, _wp_probe)


class ColoradoCaucusWixCollector:
    """Collects the Colorado House Democrats Wix caucus site.

    No RSS, no JSON API, and the /news listing server-renders only the
    newest 12 items -- the rest loads via JS. The full archive is instead
    discovered from the dynamic-news sitemap, then each detail page is
    fetched for title and date.

    The sitemap filename embeds a Wix collection GUID that can rotate, so
    the child sitemap is always resolved from /sitemap.xml by prefix match
    rather than hardcoded. <lastmod> is an edit timestamp, not a publish
    date, so it is only a low-confidence fallback behind the "Month D,
    YYYY" string in the rendered body.
    """

    method = "co_caucus_wix"
    # Detail pages are fetched one at a time, so a full-archive walk is a
    # backfill job. max_pages caps how many detail fetches a run performs.
    urls_per_page = 25

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        start = time.monotonic()
        sid = senator["official_id"]
        result = CollectorResult(official_id=sid, method=self.method)
        config = senator.get("scrape_config") or {}
        index_url = config.get("sitemap_index") or urljoin(
            senator.get("official_url", ""), "/sitemap.xml")
        sources = config.get("sources") or []

        if not index_url or not sources:
            result.errors.append("No sitemap_index / sources configured")
            return result

        async with create_client() as client:
            try:
                index_resp = await fetch_with_retry(client, index_url)
            except Exception as e:
                result.errors.append(f"Sitemap index fetch failed: {type(e).__name__}: {e}")
                return _finish(result, start, sid, self.method)

            if index_resp.status_code != 200:
                result.errors.append(
                    f"Sitemap index returned HTTP {index_resp.status_code}")
                return _finish(result, start, sid, self.method)

            child_sitemaps = re.findall(r"<loc>\s*(.*?)\s*</loc>", index_resp.text)

            for source in sources:
                match = source.get("sitemap_match")
                default_type = source.get("content_type", "press_release")
                if not match:
                    continue

                child = next((c for c in child_sitemaps if match in c), None)
                if not child:
                    result.errors.append(f"No sitemap matching '{match}' in index")
                    continue

                try:
                    child_resp = await fetch_with_retry(client, child)
                except Exception as e:
                    result.errors.append(f"Sitemap {match} fetch failed: {type(e).__name__}: {e}")
                    continue
                if child_resp.status_code != 200:
                    result.errors.append(
                        f"Sitemap {match} returned HTTP {child_resp.status_code}")
                    continue

                entries = _parse_sitemap_entries(child_resp.text)
                # lastmod is an edit timestamp, but it is still the only
                # ordering signal available before fetching detail pages.
                # Newest-first means a daily run touches the freshest items.
                entries.sort(key=lambda e: e[1] or "", reverse=True)
                budget = max_pages * self.urls_per_page

                for url, lastmod in entries[:budget]:
                    result.pages_scraped += 1
                    try:
                        detail = await fetch_with_retry(client, url)
                        await politeness_delay(0.25)
                    except Exception as e:
                        log.warning("Detail fetch failed for %s: %s", url, e)
                        continue
                    if detail.status_code != 200:
                        continue

                    soup = BeautifulSoup(detail.text, "lxml")
                    title = _wix_title(soup)
                    body_text = _wix_body(soup)
                    published_at, date_source, date_confidence = _wix_date(body_text, lastmod)

                    if not _within(since, published_at):
                        continue
                    if not title:
                        continue

                    result.releases.append(ReleaseRecord(
                        official_id=sid,
                        title=title,
                        source_url=normalize_url(url),
                        published_at=published_at,
                        body_text=body_text,
                        raw_html=detail.text,
                        content_type=_classify(title, default_type),
                        date_source=date_source,
                        date_confidence=date_confidence,
                        content_hash=content_hash(body_text or f"{title}|{url}"),
                    ))

        if not result.releases and not result.errors and not senator.get("expect_empty"):
            result.errors.append("No items found")
        return _finish(result, start, sid, self.method)

    async def health_check(self, senator: dict) -> HealthCheckResult:
        return await _health_check_json(senator, self.method, _wix_probe)


def _finish(result: CollectorResult, start: float, sid: str, method: str) -> CollectorResult:
    result.duration_seconds = time.monotonic() - start
    log.info("%s collected %d items for %s (%d fetched, %.1fs)",
             method, len(result.releases), sid,
             result.pages_scraped, result.duration_seconds)
    return result


def _parse_wp_date(raw: str | None) -> datetime | None:
    """Parse a WordPress ISO timestamp, treating naive values as UTC.

    `date_gmt` is UTC but ships without a suffix; `date` is America/Denver
    local. Prefer date_gmt at the call site so the naive-means-UTC
    assumption here is correct.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _parse_sitemap_entries(xml: str) -> list[tuple[str, str | None]]:
    """Return (url, lastmod) pairs from a sitemap document."""
    entries = []
    for block in re.findall(r"<url>(.*?)</url>", xml, re.DOTALL):
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block)
        if not loc:
            continue
        lastmod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block)
        entries.append((loc.group(1), lastmod.group(1) if lastmod else None))
    return entries


def _wix_title(soup: BeautifulSoup) -> str:
    for selector in ("h1", '[data-testid="richTextElement"] h1', "title"):
        el = soup.select_one(selector)
        if el:
            text = el.get_text(" ", strip=True)
            if text:
                # Wix appends " | Site Name" to <title>; the h1 is cleaner.
                return text.split(" | ")[0].strip()
    return ""


def _wix_body(soup: BeautifulSoup) -> str:
    for junk in soup.select("script, style, nav, form, noscript, header, footer"):
        junk.decompose()
    main = soup.select_one("main") or soup.select_one("#SITE_CONTAINER") or soup
    return main.get_text("\n", strip=True)


def _wix_date(body_text: str, lastmod: str | None) -> tuple[datetime | None, str, float]:
    """Prefer the printed date in the body; fall back to sitemap lastmod.

    Verified 2026-07-25 that the two agree on a sample, but lastmod is an
    edit timestamp and can drift when a release is corrected after
    publication, so it carries materially lower confidence.

    Every "Month D, YYYY" string in the body is tried in order, not just
    the first. Op-ed pages in the /news-1/ silo quote statutory effective
    dates and deadlines in their body copy -- one 2026 op-ed leads with
    "December 1, 2026" and "December 31, 2027" -- and taking the first
    match blindly published it four months into the future. An implausible
    candidate does not end the search.
    """
    for match in _MONTH_DAY_YEAR_PAT.finditer(body_text or ""):
        parsed = parse_date_text(match.group(1))
        if not parsed:
            continue
        value = parsed.value if hasattr(parsed, "value") else parsed
        if is_plausible_date(value):
            return value, "detail_page_text", _DETAIL_TEXT_DATE_CONFIDENCE
    if lastmod:
        try:
            dt = datetime.fromisoformat(lastmod.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt, "sitemap_lastmod", _SITEMAP_LASTMOD_CONFIDENCE
        except ValueError:
            pass
    return None, "", 0.0


async def _health_check_json(senator: dict, method: str, probe) -> HealthCheckResult:
    """Shared canary: fetch the first configured source and count items."""
    result = HealthCheckResult(
        official_id=senator["official_id"],
        allow_empty=bool(senator.get("expect_empty")),
    )
    sources = _sources(senator)
    config = senator.get("scrape_config") or {}
    target = config.get("sitemap_index") if method == "co_caucus_wix" else (
        sources[0].get("url") if sources else None)

    if not target:
        result.error_message = "No source configured"
        return result

    start = time.monotonic()
    async with create_client() as client:
        try:
            resp = await fetch_with_retry(client, probe(target))
        except Exception as e:
            result.error_message = f"{type(e).__name__}: {e}"
            return result
        result.page_load_ms = int((time.monotonic() - start) * 1000)
        result.url_status = resp.status_code
        if resp.status_code != 200:
            result.error_message = f"HTTP {resp.status_code}"
            return result
        try:
            count, dated = _probe_counts(method, resp.text)
        except Exception as e:
            result.error_message = f"Parse failed: {type(e).__name__}: {e}"
            return result

    result.items_found = count
    result.selector_ok = count > 0
    result.date_parseable = dated
    return result


def _probe_counts(method: str, text: str) -> tuple[int, bool]:
    if method == "co_caucus_wix":
        return len(re.findall(r"<loc>", text)), True
    payload = json.loads(text)
    if method == "co_caucus_wp":
        return len(payload), bool(payload and payload[0].get("date"))
    items = payload.get("items") or []
    return len(items), bool(items and items[0].get("publishOn"))


def _squarespace_probe(url: str) -> str:
    return f"{url}?format=json"


def _wp_probe(url: str) -> str:
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}per_page=5"


def _wix_probe(url: str) -> str:
    return url
