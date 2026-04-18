"""
Unified date parsing for Capitol Releases.

Consolidates date extraction logic from backfill.py, backfill_playwright.py,
and repair_dates.py into a single module. Every extracted date carries
provenance (source + confidence) for archival trust.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class DateResult:
    """A parsed date with provenance metadata."""
    value: datetime
    source: str       # feed, meta_tag, json_ld, time_element, url_path, page_text, css_selector, unknown
    confidence: float  # 0.0 - 1.0


MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

# Compiled patterns for text-based date parsing
_PAT_MDY_TEXT = re.compile(
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*)"
    r"\s+(\d{1,2}),?\s+(\d{4})",
    re.I,
)
_PAT_MDY_NUMERIC = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})")
_PAT_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

# URL path patterns
_PAT_URL_YMD = re.compile(r"/(\d{4})/(\d{1,2})/(\d{1,2})/")
_PAT_URL_YM = re.compile(r"/(\d{4})/(\d{1,2})/(?!\d)")
_PAT_URL_MDY = re.compile(r"/(\d{2})/(\d{2})/(\d{4})/")


def parse_date_text(text: str) -> DateResult | None:
    """Parse a date from a text string.

    Handles: "April 15, 2026", "Apr 15, 2026", "04/15/2026",
    "4.15.26", "2026-04-15".

    Returns DateResult with source='page_text' or None.
    """
    if not text:
        return None
    text = text.strip()

    # "April 15, 2026" or "Apr 15 2026"
    m = _PAT_MDY_TEXT.search(text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            try:
                dt = datetime(int(m.group(3)), month, int(m.group(2)),
                              tzinfo=timezone.utc)
                return DateResult(value=dt, source="page_text", confidence=0.85)
            except ValueError:
                pass

    # "04/15/2026" or "4.15.26"
    m = _PAT_MDY_NUMERIC.search(text)
    if m:
        try:
            year = int(m.group(3))
            if year < 100:
                year += 2000
            dt = datetime(year, int(m.group(1)), int(m.group(2)),
                          tzinfo=timezone.utc)
            return DateResult(value=dt, source="page_text", confidence=0.75)
        except ValueError:
            pass

    # "2026-04-15"
    m = _PAT_ISO.search(text)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                          tzinfo=timezone.utc)
            return DateResult(value=dt, source="page_text", confidence=0.90)
        except ValueError:
            pass

    return None


def extract_date_from_url(url: str) -> DateResult | None:
    """Extract a date embedded in a URL path.

    Handles: /2026/04/15/, /2026/04/, /04/15/2026/
    """
    if not url:
        return None

    # /YYYY/MM/DD/
    m = _PAT_URL_YMD.search(url)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                          tzinfo=timezone.utc)
            return DateResult(value=dt, source="url_path", confidence=0.90)
        except ValueError:
            pass

    # /YYYY/MM/ (day defaults to 1)
    m = _PAT_URL_YM.search(url)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), 1,
                          tzinfo=timezone.utc)
            return DateResult(value=dt, source="url_path", confidence=0.70)
        except ValueError:
            pass

    # /MM/DD/YYYY/
    m = _PAT_URL_MDY.search(url)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)),
                          tzinfo=timezone.utc)
            return DateResult(value=dt, source="url_path", confidence=0.80)
        except ValueError:
            pass

    return None


def _parse_iso_datetime(raw: str) -> datetime | None:
    """Parse an ISO datetime string, handling Z and missing timezone."""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, TypeError):
        return None


def extract_date_from_html(soup) -> DateResult | None:
    """Extract publication date from HTML using structured metadata.

    Tries in order: OpenGraph/meta tags, JSON-LD, <time> elements,
    common CSS date containers, then body text fallback.

    Args:
        soup: BeautifulSoup object of the page.
    """
    # 1. OpenGraph / meta tags (highest confidence)
    for attr in ["article:published_time", "og:article:published_time",
                 "datePublished", "date", "DC.date.issued", "pubdate"]:
        meta = (soup.find("meta", property=attr)
                or soup.find("meta", attrs={"name": attr}))
        if meta and meta.get("content"):
            dt = _parse_iso_datetime(meta["content"])
            if dt:
                return DateResult(value=dt, source="meta_tag", confidence=0.95)

    # 2. JSON-LD
    for script in soup.select("script[type='application/ld+json']"):
        text = script.get_text()
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', text)
        if m:
            dt = _parse_iso_datetime(m.group(1))
            if dt:
                return DateResult(value=dt, source="json_ld", confidence=0.95)

    # 3. <time> element with datetime attribute
    time_el = soup.select_one("time[datetime]")
    if time_el:
        dt = _parse_iso_datetime(time_el["datetime"])
        if dt:
            return DateResult(value=dt, source="time_element", confidence=0.90)

    # 4. <time> element with text content
    time_el = soup.select_one("time")
    if time_el:
        result = parse_date_text(time_el.get_text(strip=True))
        if result:
            result.source = "time_element"
            result.confidence = 0.85
            return result

    # 5. Date-like text in common CSS containers
    date_selectors = [
        ".date", ".post-date", ".entry-date", ".published",
        ".ArticleBlock__date", ".press-release-date",
        ".field-name-field-date", ".post-media-list-date",
        "span.datetime", ".recordListDate", ".pressDate",
    ]
    for sel in date_selectors:
        el = soup.select_one(sel)
        if el:
            result = parse_date_text(el.get_text(strip=True))
            if result:
                result.source = "css_selector"
                result.confidence = 0.80
                return result

    # 6. Fallback: date in first 1000 chars of body text
    # (ColdFusion sites like Graham have ~700 chars of nav before the date)
    body = soup.select_one("main") or soup.select_one("article") or soup.body
    if body:
        text = body.get_text(" ", strip=True)[:1000]
        result = parse_date_text(text)
        if result:
            result.confidence = 0.50  # low confidence for body text extraction
            return result

    return None


def extract_date(
    text: str | None = None,
    url: str | None = None,
    soup=None,
) -> DateResult | None:
    """Try all date extraction methods in priority order.

    Returns the highest-confidence DateResult found, or None.
    """
    candidates: list[DateResult] = []

    # HTML metadata is highest quality
    if soup is not None:
        result = extract_date_from_html(soup)
        if result:
            candidates.append(result)

    # URL path dates are reliable
    if url:
        result = extract_date_from_url(url)
        if result:
            candidates.append(result)

    # Text parsing is the fallback
    if text:
        result = parse_date_text(text)
        if result:
            candidates.append(result)

    if not candidates:
        return None

    # Return highest confidence
    return max(candidates, key=lambda r: r.confidence)
