"""State legislature collectors.

These are source-family collectors for early state expansion. They are
registered behind explicit collection_method values so they do not affect
existing federal/Texas behavior.
"""

import logging
import time
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from pipeline.collectors.base import CollectorResult, HealthCheckResult, ReleaseRecord
from pipeline.lib.classifier import classify_content_type
from pipeline.lib.dates import extract_date_from_html, extract_date_from_url, parse_date_text
from pipeline.lib.http import create_client, fetch_with_retry, politeness_delay
from pipeline.lib.identity import content_hash, normalize_url

log = logging.getLogger("capitol.collector.state_legislature")


class NebraskaUnicameralCollector:
    """Collects Nebraska Unicameral district WordPress posts."""

    method = "ne_unicameral"

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        start = time.monotonic()
        sid = senator["senator_id"]
        pr_url = senator.get("press_release_url", "")
        result = CollectorResult(senator_id=sid, method=self.method)

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
                items = _extract_listing_items(soup, current_url)

                if not items:
                    if page == 1 and not senator.get("expect_empty"):
                        result.errors.append("No items found on page 1")
                    break

                result.pages_scraped = page
                page_dates = [item["published_at"] for item in items if item["published_at"]]

                for item in items:
                    published_at = item["published_at"]
                    if since and published_at and published_at.date() < since.date():
                        continue

                    title = item["title"]
                    body_text = item["body_text"]
                    raw_html = item["raw_html"]
                    date_source = item["date_source"]
                    date_confidence = item["date_confidence"]

                    try:
                        detail_resp = await fetch_with_retry(client, item["source_url"])
                        await politeness_delay(0.2)
                        if detail_resp.status_code == 200:
                            raw_html = detail_resp.text
                            detail_soup = BeautifulSoup(raw_html, "lxml")
                            detail_title = _extract_detail_title(detail_soup)
                            if detail_title:
                                title = detail_title
                            detail_body = _extract_body_text(detail_soup)
                            if detail_body:
                                body_text = detail_body
                            detail_date = extract_date_from_html(detail_soup)
                            if detail_date and detail_date.confidence > date_confidence:
                                published_at = detail_date.value
                                date_source = detail_date.source
                                date_confidence = detail_date.confidence
                    except Exception as e:
                        log.warning("Detail page failed for %s: %s", item["source_url"], e)

                    record = ReleaseRecord(
                        senator_id=sid,
                        title=title,
                        source_url=normalize_url(item["source_url"]),
                        published_at=published_at,
                        body_text=body_text,
                        raw_html=raw_html,
                        content_type=_classify_content(title),
                        date_source=date_source,
                        date_confidence=date_confidence,
                        content_hash=content_hash(body_text or f"{title}|{item['source_url']}"),
                    )
                    result.releases.append(record)

                if since and page_dates and max(dt.date() for dt in page_dates) < since.date():
                    break

                if page >= max_pages:
                    break

                next_url = _find_next_page(soup, current_url)
                if not next_url or next_url == current_url:
                    break
                current_url = next_url
                await politeness_delay(0.4)

        result.duration_seconds = time.monotonic() - start
        log.info(
            "ne_unicameral collected %d items for %s (%d pages, %.1fs)",
            len(result.releases),
            sid,
            result.pages_scraped,
            result.duration_seconds,
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
        items = _extract_listing_items(soup, pr_url)
        result.items_found = len(items)
        result.selector_ok = bool(items) or bool(senator.get("expect_empty"))
        result.date_parseable = any(item["published_at"] for item in items)
        return result


def _extract_listing_items(soup: BeautifulSoup, base_url: str) -> list[dict]:
    items: list[dict] = []
    for card in soup.select("div.card[id^='post-']"):
        header = card.select_one(".card-header")
        if not header:
            continue

        link = header.select_one("a[rel='bookmark'][href]")
        if not link:
            continue

        title = link.get_text(" ", strip=True)
        if not title:
            title = (link.get("title") or "").removeprefix("Permanent Link to ").strip()
        if not title:
            continue

        source_url = normalize_url(urljoin(base_url, link["href"]))
        date_text = ""
        date_el = header.select_one("small")
        if date_el:
            date_text = date_el.get_text(" ", strip=True)

        date_result = parse_date_text(date_text) or extract_date_from_url(source_url)
        published_at = date_result.value if date_result else None
        date_source = "listing_text" if date_result and date_result.source == "page_text" else (date_result.source if date_result else "")
        date_confidence = 0.95 if date_result and date_result.source == "page_text" else (date_result.confidence if date_result else 0.0)

        body = card.select_one(".entry")
        body_text = _clean_text(body) if body else ""

        items.append({
            "title": title,
            "source_url": source_url,
            "published_at": published_at,
            "body_text": body_text,
            "raw_html": str(card),
            "date_source": date_source,
            "date_confidence": date_confidence,
        })
    return items


def _extract_detail_title(soup: BeautifulSoup) -> str:
    link = soup.select_one("div.card[id^='post-'] .card-header a[rel='bookmark']")
    if link:
        return link.get_text(" ", strip=True)
    h1 = soup.select_one("h1")
    return h1.get_text(" ", strip=True) if h1 else ""


def _extract_body_text(soup: BeautifulSoup) -> str:
    body = soup.select_one("div.card[id^='post-'] .entry")
    return _clean_text(body) if body else ""


def _clean_text(el: Tag | None) -> str:
    if not el:
        return ""
    for junk in el.select("script, style, nav, form"):
        junk.decompose()
    return el.get_text("\n", strip=True)


def _find_next_page(soup: BeautifulSoup, base_url: str) -> str:
    link = soup.select_one("ul.pager li.previous a[href]")
    if not link:
        return ""
    return normalize_url(urljoin(base_url, link["href"]))


def _classify_content(title: str) -> str:
    lowered = title.lower()
    if "statement" in lowered:
        return "statement"
    if "press release" in lowered or lowered.startswith(("release:", "news release:")):
        return "press_release"
    if "newsletter" in lowered or "legislative desk" in lowered:
        return "blog"
    return "blog"


class CaliforniaSenateCollector:
    """Collects California Senate district press-release pages."""

    method = "ca_senate"

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        return await _collect_listing_source(
            senator=senator,
            since=since,
            max_pages=max_pages,
            method=self.method,
            item_extractor=_extract_ca_items,
            next_page_finder=_find_ca_next_page,
            body_selector="main article, article, main",
        )

    async def health_check(self, senator: dict) -> HealthCheckResult:
        return await _health_check_listing_source(senator, self.method, _extract_ca_items)


class OhioSenateCollector:
    """Collects Ohio Senate member news pages."""

    method = "oh_senate"

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        return await _collect_listing_source(
            senator=senator,
            since=since,
            max_pages=max_pages,
            method=self.method,
            item_extractor=_extract_oh_items,
            next_page_finder=_find_oh_next_page,
            body_selector="main article, main .content-frame, main",
        )

    async def health_check(self, senator: dict) -> HealthCheckResult:
        return await _health_check_listing_source(senator, self.method, _extract_oh_items)


class MissouriSenateNewsroomCollector:
    """Collects Missouri Senate central newsroom items."""

    method = "mo_senate_newsroom"

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        return await _collect_listing_source(
            senator=senator,
            since=since,
            max_pages=max_pages,
            method=self.method,
            item_extractor=_extract_mo_items,
            next_page_finder=_find_no_next_page,
            body_selector="main, .main-container",
        )

    async def health_check(self, senator: dict) -> HealthCheckResult:
        return await _health_check_listing_source(senator, self.method, _extract_mo_items)


class WVLegislatureNewsCollector:
    """Collects West Virginia Legislature central news-release rows."""

    method = "wv_legislature_news"

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        return await _collect_listing_source(
            senator=senator,
            since=since,
            max_pages=max_pages,
            method=self.method,
            item_extractor=_extract_wv_items,
            next_page_finder=_find_no_next_page,
            body_selector="main, body",
            prefer_detail_title=False,
        )

    async def health_check(self, senator: dict) -> HealthCheckResult:
        return await _health_check_listing_source(senator, self.method, _extract_wv_items)


async def _collect_listing_source(
    *,
    senator: dict,
    since: datetime | None,
    max_pages: int,
    method: str,
    item_extractor,
    next_page_finder,
    body_selector: str,
    prefer_detail_title: bool = True,
) -> CollectorResult:
    start = time.monotonic()
    sid = senator["senator_id"]
    pr_url = senator.get("press_release_url", "")
    result = CollectorResult(senator_id=sid, method=method)

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
            items = item_extractor(soup, current_url)
            if not items:
                if page == 1 and not senator.get("expect_empty"):
                    result.errors.append("No items found on page 1")
                break

            result.pages_scraped = page
            page_dates = [item["published_at"] for item in items if item.get("published_at")]
            for item in items:
                published_at = item.get("published_at")
                if since and published_at and published_at.date() < since.date():
                    continue

                title = item["title"]
                source_url = item["source_url"]
                body_text = item.get("body_text", "")
                raw_html = item.get("raw_html", "")
                date_source = item.get("date_source", "")
                date_confidence = item.get("date_confidence", 0.0)

                try:
                    detail_resp = await fetch_with_retry(client, source_url)
                    await politeness_delay(0.2)
                    if detail_resp.status_code == 200:
                        raw_html = detail_resp.text
                        detail_soup = BeautifulSoup(raw_html, "lxml")
                        detail_title = _detail_title(detail_soup)
                        if prefer_detail_title and detail_title and len(detail_title) < 400:
                            title = detail_title
                        detail_body = _extract_by_selector(detail_soup, body_selector)
                        if detail_body:
                            body_text = detail_body
                        detail_date = extract_date_from_html(detail_soup)
                        if detail_date and detail_date.confidence > date_confidence:
                            published_at = detail_date.value
                            date_source = detail_date.source
                            date_confidence = detail_date.confidence
                except Exception as e:
                    log.warning("Detail page failed for %s: %s", source_url, e)

                result.releases.append(ReleaseRecord(
                    senator_id=sid,
                    title=title,
                    source_url=normalize_url(source_url),
                    published_at=published_at,
                    body_text=body_text,
                    raw_html=raw_html,
                    content_type=classify_content_type(title=title, url=source_url),
                    date_source=date_source,
                    date_confidence=date_confidence,
                    content_hash=content_hash(body_text or f"{title}|{source_url}"),
                ))

            if since and page_dates and max(dt.date() for dt in page_dates) < since.date():
                break
            if page >= max_pages:
                break
            next_url = next_page_finder(soup, current_url)
            if not next_url or next_url == current_url:
                break
            current_url = next_url
            await politeness_delay(0.4)

    result.duration_seconds = time.monotonic() - start
    log.info("%s collected %d items for %s (%d pages, %.1fs)",
             method, len(result.releases), sid, result.pages_scraped, result.duration_seconds)
    return result


async def _health_check_listing_source(senator: dict, method: str, item_extractor) -> HealthCheckResult:
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
    items = item_extractor(soup, pr_url)
    result.items_found = len(items)
    result.allow_empty = bool(senator.get("expect_empty"))
    result.selector_ok = bool(items) or result.allow_empty
    result.date_parseable = any(item.get("published_at") for item in items)
    return result


def _extract_ca_items(soup: BeautifulSoup, base_url: str) -> list[dict]:
    rows = soup.select(".view-content > div")
    if not rows:
        rows = soup.select(".views-row")
    items = []
    for row in rows:
        link = row.select_one('a[href*="/news/press-release/"]')
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        text = row.get_text(" ", strip=True)
        date_result = parse_date_text(text) or extract_date_from_url(link["href"])
        items.append(_listing_item(
            title=title,
            source_url=urljoin(base_url, link["href"]),
            date_result=date_result,
            raw_html=str(row),
            body_text=text,
        ))
    return items


def _find_ca_next_page(soup: BeautifulSoup, base_url: str) -> str:
    link = soup.select_one('li.pager__item--next a[href], a[rel="next"][href], .pager-next a[href]')
    return normalize_url(urljoin(base_url, link["href"])) if link else ""


def _extract_oh_items(soup: BeautifulSoup, base_url: str) -> list[dict]:
    items = []
    for row in soup.select("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        link = row.select_one('a[href*="/news/"], a[href^="news/"]')
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        date_result = parse_date_text(cells[0].get_text(" ", strip=True))
        items.append(_listing_item(
            title=title,
            source_url=urljoin(base_url, link["href"]),
            date_result=date_result,
            raw_html=str(row),
            body_text=row.get_text(" ", strip=True),
        ))
    return items


def _find_oh_next_page(soup: BeautifulSoup, base_url: str) -> str:
    for link in soup.select('a[href*="start="]'):
        if "next page" in link.get_text(" ", strip=True).lower() or "Next Page" in str(link):
            return normalize_url(urljoin(base_url, link["href"]))
    return ""


def _extract_mo_items(soup: BeautifulSoup, base_url: str) -> list[dict]:
    items = []
    for link in soup.select('a[href*="/Media/NewsDetails"], a[href*="/media/newsdetails"]'):
        card = link.select_one(".accent-item") or link
        title_el = card.select_one(".fs-3")
        date_el = card.select_one(".heading--label")
        title = title_el.get_text(" ", strip=True) if title_el else link.get("aria-label", "")
        title = title.removeprefix("View ").strip()
        if not title:
            continue
        date_result = parse_date_text(date_el.get_text(" ", strip=True) if date_el else card.get_text(" ", strip=True))
        items.append(_listing_item(
            title=title,
            source_url=urljoin(base_url, link["href"]),
            date_result=date_result,
            raw_html=str(card),
            body_text=card.get_text(" ", strip=True),
        ))
    return items


def _extract_wv_items(soup: BeautifulSoup, base_url: str) -> list[dict]:
    items = []
    skip_phrases = ("calendar and committee schedule",)
    for row in soup.select("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        link = row.select_one('a[href*="pressrelease.cfm"]')
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        if any(phrase in title.lower() for phrase in skip_phrases):
            continue
        date_result = parse_date_text(cells[-1].get_text(" ", strip=True))
        author = cells[0].get_text(" ", strip=True)
        body_text = f"{author} | {row.get_text(' ', strip=True)}"
        items.append(_listing_item(
            title=title,
            source_url=urljoin(base_url, link["href"]),
            date_result=date_result,
            raw_html=str(row),
            body_text=body_text,
        ))
    return items


def _find_no_next_page(soup: BeautifulSoup, base_url: str) -> str:
    return ""


def _listing_item(
    *,
    title: str,
    source_url: str,
    date_result,
    raw_html: str,
    body_text: str,
) -> dict:
    return {
        "title": title,
        "source_url": normalize_url(source_url),
        "published_at": date_result.value if date_result else None,
        "body_text": body_text,
        "raw_html": raw_html,
        "date_source": date_result.source if date_result else "",
        "date_confidence": date_result.confidence if date_result else 0.0,
    }


def _detail_title(soup: BeautifulSoup) -> str:
    og = soup.select_one('meta[property="og:title"], meta[name="og:title"]')
    if og and og.get("content"):
        return og["content"].strip()
    h1 = soup.select_one("h1")
    return h1.get_text(" ", strip=True) if h1 else ""


def _extract_by_selector(soup: BeautifulSoup, selectors: str) -> str:
    for sel in [s.strip() for s in selectors.split(",") if s.strip()]:
        el = soup.select_one(sel)
        text = _clean_text(el) if el else ""
        if len(text) > 100:
            return text
    return ""
