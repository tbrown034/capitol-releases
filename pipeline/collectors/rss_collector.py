"""
RSS-based collector for Capitol Releases.

The most reliable collection method. RSS feeds are structurally
incapable of breaking due to selector changes. For the 38 senators
with RSS feeds, this collector handles daily updates with zero
selector maintenance.
"""

import logging
import time
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from pipeline.collectors.base import Collector, CollectorResult, ReleaseRecord, HealthCheckResult
from pipeline.lib.classifier import classify_content_type, is_external_content
from pipeline.lib.dates import parse_date_text, DateResult
from pipeline.lib.http import create_client, fetch_with_retry, politeness_delay
from pipeline.lib.identity import normalize_url, content_hash
from pipeline.lib.rss import parse_feed_items, _looks_like_feed

log = logging.getLogger("capitol.collector.rss")


class RSSCollector:
    """Collects press releases via RSS feeds."""

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        start = time.monotonic()
        sid = senator["senator_id"]
        feed_url = senator.get("rss_feed_url", "")
        result = CollectorResult(senator_id=sid, method="rss")

        if not feed_url:
            result.errors.append("No RSS feed URL configured")
            return result

        async with create_client() as client:
            try:
                resp = await fetch_with_retry(client, feed_url)
            except Exception as e:
                result.errors.append(f"Feed fetch failed: {type(e).__name__}: {e}")
                result.duration_seconds = time.monotonic() - start
                return result

            if resp.status_code != 200:
                result.errors.append(f"Feed returned HTTP {resp.status_code}")
                result.duration_seconds = time.monotonic() - start
                return result

            # Parse the feed
            items = parse_feed_items(resp.text)
            result.pages_scraped = 1

            for item in items:
                # Skip external content (In the News links)
                if is_external_content(item.url, item.title):
                    continue

                # Skip items before the cutoff
                if since and item.published_at and item.published_at < since:
                    continue

                # Classify content type
                ctype = classify_content_type(
                    title=item.title,
                    url=item.url,
                    categories=item.categories,
                )

                # Date provenance
                date_source = "feed"
                date_confidence = 0.95 if item.published_at else 0.0

                # Fetch detail page for full body text
                body_text = ""
                raw_html = ""
                if item.url:
                    try:
                        detail_resp = await fetch_with_retry(client, item.url)
                        await politeness_delay(0.3)
                        if detail_resp.status_code == 200:
                            raw_html = detail_resp.text
                            soup = BeautifulSoup(raw_html, "lxml")
                            body_text = _extract_body(soup)

                            # If feed didn't have a date, try the detail page
                            if not item.published_at:
                                from pipeline.lib.dates import extract_date_from_html
                                date_result = extract_date_from_html(soup)
                                if date_result:
                                    item.published_at = date_result.value
                                    date_source = date_result.source
                                    date_confidence = date_result.confidence
                    except Exception as e:
                        log.warning("Detail page failed for %s: %s", item.url, e)

                # Future-dated typos: keep the date but flag confidence.
                if item.published_at:
                    from datetime import datetime as _dt, timezone as _tz
                    _now = _dt.now(_tz.utc)
                    _pd = item.published_at if item.published_at.tzinfo else item.published_at.replace(tzinfo=_tz.utc)
                    if (_pd - _now).total_seconds() > 86400:
                        log.warning(
                            "Future-dated release flagged (rss): %s claims %s; demoting confidence",
                            item.url, item.published_at.isoformat(),
                        )
                        date_source = f"{date_source}_future_typo"
                        date_confidence = min(date_confidence, 0.2)

                record = ReleaseRecord(
                    senator_id=sid,
                    title=item.title,
                    source_url=normalize_url(item.url),
                    published_at=item.published_at,
                    body_text=body_text,
                    raw_html=raw_html,
                    content_type=ctype,
                    date_source=date_source,
                    date_confidence=date_confidence,
                    content_hash=content_hash(body_text),
                )
                result.releases.append(record)

        result.duration_seconds = time.monotonic() - start
        log.info(
            "RSS collected %d releases for %s in %.1fs",
            len(result.releases), sid, result.duration_seconds,
        )
        return result

    async def health_check(self, senator: dict) -> HealthCheckResult:
        sid = senator["senator_id"]
        feed_url = senator.get("rss_feed_url", "")
        hc = HealthCheckResult(senator_id=sid)

        if not feed_url:
            hc.error_message = "No RSS feed URL"
            return hc

        start = time.monotonic()
        async with create_client() as client:
            try:
                resp = await client.get(feed_url, follow_redirects=True)
                hc.url_status = resp.status_code
                hc.page_load_ms = int((time.monotonic() - start) * 1000)

                if resp.status_code == 200:
                    feed_type = _looks_like_feed(
                        resp.headers.get("content-type", ""), resp.text
                    )
                    if feed_type:
                        items = parse_feed_items(resp.text)
                        hc.items_found = len(items)
                        hc.selector_ok = True
                        hc.date_parseable = any(i.published_at for i in items)
            except Exception as e:
                hc.error_message = f"{type(e).__name__}: {e}"
                hc.page_load_ms = int((time.monotonic() - start) * 1000)

        return hc


def _extract_body(soup: BeautifulSoup) -> str:
    """Extract main body text from a detail page.

    Tries specific content selectors first, falls back to largest
    text block in main/article.
    """
    for sel in [
        "article .entry-content",
        ".post-content",
        ".field-name-body",
        "main article",
        ".bodycopy",
        "main .content",
        ".press-release-content",
        ".Heading--body",
    ]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(" ", strip=True)
            if len(text) > 100:
                return text

    # Fallback: largest text block in main or article
    container = soup.select_one("main") or soup.select_one("article") or soup.body
    if container:
        return container.get_text(" ", strip=True)[:5000]

    return ""
