"""
HTTP-based collector for Capitol Releases.

Handles senators with static HTML press release pages. Reuses the
battle-tested selector logic from backfill.py while adding retry,
classification, and provenance.

For daily updates: page 1 only, stop when hitting known URLs.
For backfill: multiple pages with configurable depth.
"""

import logging
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from pipeline.collectors.base import Collector, CollectorResult, ReleaseRecord, HealthCheckResult
from pipeline.lib.classifier import classify_content_type, is_external_content, is_listing_url
from pipeline.lib.dates import parse_date_text, extract_date_from_url, extract_date, demote_if_future
from pipeline.lib.http import create_client, fetch_with_retry, politeness_delay
from pipeline.lib.identity import normalize_url, content_hash

# Import the existing selector/pagination logic from backfill.py
# These will be extracted into lib/selectors.py in a future refactor
from pipeline.backfill import (
    extract_listing_items,
    extract_item_data,
    extract_body_text,
    find_next_page,
    parse_date,
)

log = logging.getLogger("capitol.collector.httpx")


class HttpxCollector:
    """Collects press releases via HTTP + CSS selectors."""

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        start = time.monotonic()
        sid = senator["senator_id"]
        pr_url = senator.get("press_release_url", "")
        selectors = senator.get("selectors", {}) or {}
        result = CollectorResult(senator_id=sid, method="httpx")

        if not pr_url:
            result.errors.append("No press_release_url configured")
            return result

        async with create_client() as client:
            current_url = pr_url
            page = 0

            while current_url and page < max_pages:
                page += 1
                try:
                    resp = await fetch_with_retry(client, current_url)
                except Exception as e:
                    result.errors.append(f"Page {page} fetch failed: {type(e).__name__}: {e}")
                    break

                if resp.status_code != 200:
                    result.errors.append(f"Page {page} returned HTTP {resp.status_code}")
                    break

                soup = BeautifulSoup(resp.text, "lxml")
                items = extract_listing_items(soup, selectors)

                if not items:
                    if page == 1:
                        result.errors.append("No items found on page 1")
                    break

                result.pages_scraped = page
                stop = False

                for item in items:
                    title, date_text, detail_url = extract_item_data(item, current_url, selectors)

                    if not title or not detail_url:
                        continue

                    # Skip external content (non-.gov, social media, news aggregators)
                    if is_external_content(detail_url, title):
                        continue

                    # Skip listing/index pages misclassified as detail URLs
                    if is_listing_url(detail_url):
                        log.debug("Skipping listing-page URL: %s", detail_url)
                        continue

                    # Parse date with provenance
                    date_result = None
                    pub_date = None
                    date_source = ""
                    date_confidence = 0.0

                    if date_text:
                        date_result = parse_date_text(date_text)
                    if not date_result and detail_url:
                        date_result = extract_date_from_url(detail_url)
                    if date_result:
                        pub_date = date_result.value
                        date_source = date_result.source
                        date_confidence = date_result.confidence

                    # Check cutoff. Compare on date boundaries because many
                    # listing pages emit dates with no time component, so
                    # parse_date_text returns midnight UTC. A timestamp-level
                    # compare against `since` (the previous run's finished_at)
                    # would always evaluate True and cause the loop to break
                    # on item 0, silently truncating collection.
                    # Use `continue` rather than `break` so out-of-order
                    # listings don't cause us to miss later items.
                    if since and pub_date and pub_date.date() < since.date():
                        continue

                    # Classify content type
                    ctype = classify_content_type(title=title, url=detail_url)

                    # Fetch detail page for body text
                    body_text = ""
                    raw_html = ""
                    try:
                        detail_resp = await fetch_with_retry(client, detail_url)
                        await politeness_delay(0.3)
                        if detail_resp.status_code == 200:
                            raw_html = detail_resp.text
                            detail_soup = BeautifulSoup(raw_html, "lxml")
                            body_text = extract_body_text(detail_soup)

                            # Canonical title from detail page: prefer og:title
                            # over list-page title. List cards sometimes wrap
                            # date + title + excerpt in a single anchor, and
                            # the generic get_text() fallback captures all of
                            # it. og:title / <h1> is always the clean headline.
                            canonical_title = None
                            og = detail_soup.select_one('meta[property="og:title"]')
                            if og and og.get("content"):
                                canonical_title = og["content"].strip()
                            if not canonical_title:
                                h1 = detail_soup.select_one("h1")
                                if h1:
                                    canonical_title = h1.get_text(strip=True)
                            if canonical_title and 5 < len(canonical_title) < 400:
                                if len(title) > len(canonical_title) * 1.5 or len(title) > 250:
                                    title = canonical_title

                            # Always probe the detail page — meta tags (confidence
                            # 0.95) beat URL-path dates (0.70–0.90), and many
                            # senate-generic sites expose /YYYY/M/slug URLs where
                            # the day defaults to 1 and silently clumps every
                            # record to first-of-month.
                            from pipeline.lib.dates import extract_date_from_html
                            html_date = extract_date_from_html(detail_soup)
                            if html_date and html_date.confidence > date_confidence:
                                pub_date = html_date.value
                                date_source = html_date.source
                                date_confidence = html_date.confidence

                    except Exception as e:
                        log.warning("Detail page failed for %s: %s", detail_url, e)

                    # Future-dated typos: keep the extracted date but flag
                    # confidence so downstream sorts/quality treat it as
                    # suspect. Most of these are press-office month typos
                    # (e.g. "May 04" on a release captured April 28).
                    if pub_date:
                        from datetime import datetime as _dt, timezone as _tz
                        _now = _dt.now(_tz.utc)
                        _pd = pub_date if pub_date.tzinfo else pub_date.replace(tzinfo=_tz.utc)
                        if (_pd - _now).total_seconds() > 86400:
                            log.warning(
                                "Future-dated release flagged: %s claims %s, captured now (%s); demoting confidence",
                                detail_url, pub_date.isoformat(), _now.isoformat(),
                            )
                            date_source = f"{date_source}_future_typo" if date_source else "future_typo"
                            date_confidence = min(date_confidence, 0.2)

                    record = ReleaseRecord(
                        senator_id=sid,
                        title=title,
                        source_url=normalize_url(detail_url),
                        published_at=pub_date,
                        body_text=body_text,
                        raw_html=raw_html,
                        content_type=ctype,
                        date_source=date_source,
                        date_confidence=date_confidence,
                        content_hash=content_hash(body_text),
                    )
                    result.releases.append(record)

                if stop:
                    break

                # Find next page (only if max_pages > 1)
                if page < max_pages:
                    next_url = find_next_page(soup, current_url)
                    if next_url and next_url != current_url:
                        current_url = next_url
                        await politeness_delay(0.5)
                    else:
                        break
                else:
                    break

        result.duration_seconds = time.monotonic() - start
        log.info(
            "httpx collected %d releases for %s (%d pages, %.1fs)",
            len(result.releases), sid, result.pages_scraped, result.duration_seconds,
        )
        return result

    async def health_check(self, senator: dict) -> HealthCheckResult:
        sid = senator["senator_id"]
        pr_url = senator.get("press_release_url", "")
        selectors = senator.get("selectors", {}) or {}
        hc = HealthCheckResult(senator_id=sid)

        if not pr_url:
            hc.error_message = "No press_release_url"
            return hc

        start = time.monotonic()
        async with create_client() as client:
            try:
                resp = await client.get(pr_url, follow_redirects=True)
                hc.url_status = resp.status_code
                hc.page_load_ms = int((time.monotonic() - start) * 1000)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    items = extract_listing_items(soup, selectors)
                    hc.items_found = len(items)
                    hc.selector_ok = len(items) > 0

                    if items:
                        # Check if we can parse a date from the first item
                        title, date_text, detail_url = extract_item_data(items[0], pr_url, selectors)
                        if date_text:
                            dr = parse_date_text(date_text)
                            hc.date_parseable = dr is not None
            except Exception as e:
                hc.error_message = f"{type(e).__name__}: {e}"
                hc.page_load_ms = int((time.monotonic() - start) * 1000)

        return hc
