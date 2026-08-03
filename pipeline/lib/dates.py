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
# Accepts optional ordinal suffix (e.g. "April 17th, 2026") that some
# senate-custom CMS templates (Heinrich) emit.
_PAT_MDY_TEXT = re.compile(
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})",
    re.I,
)
_PAT_MDY_NUMERIC = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})")
_PAT_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

# Sanity bounds for an extracted publication date. Deliberately loose —
# silo backfills legitimately reach pre-2025 archives — but tight enough
# to reject template constants and press-office month typos. A candidate
# outside these bounds does not end the search; the chain keeps looking
# for a plausible alternative and only falls back to the implausible one
# if nothing better exists (never silently drop a date we did extract).
PLAUSIBLE_FLOOR = datetime(2000, 1, 1, tzinfo=timezone.utc)
FUTURE_TOLERANCE_DAYS = 1

# Containers whose dates belong to *other* articles: related-news rails,
# "recent posts" sidebars, nav and footer chrome. The House ASPX
# "documentsingle.aspx" template renders a related-docs module
# (div.news-related-news) ahead of the article body in document order, so
# an unscoped `soup.select_one("time")` reads a neighbouring article's
# date instead of this one's.
_RELATED_CONTAINER_PAT = re.compile(
    r"related|sidebar|recent-?news|recent-?posts|more-?news|latest-?news"
    r"|popular|footer|breadcrumb|site-?nav|navbar",
    re.I,
)

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


def is_plausible_date(dt: datetime | None, now: datetime | None = None) -> bool:
    """True if `dt` could be a real publication date for this corpus.

    Rejects template constants stuck in the distant past and dates more
    than a day in the future. Used to keep walking the extraction chain
    rather than returning the first structurally-valid but absurd value.
    """
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if dt < PLAUSIBLE_FLOOR:
        return False
    return (dt - reference).total_seconds() <= FUTURE_TOLERANCE_DAYS * 86400


def _in_related_module(el) -> bool:
    """True if `el` sits inside a related-content, sidebar or nav module.

    Walks a bounded number of ancestors so a deeply-nested page body is
    never mistaken for chrome.
    """
    node = getattr(el, "parent", None)
    for _ in range(8):
        if node is None or getattr(node, "name", None) in ("body", "html", "[document]"):
            break
        classes = node.get("class") or []
        tokens = " ".join(classes) + " " + (node.get("id") or "")
        if _RELATED_CONTAINER_PAT.search(tokens):
            return True
        node = node.parent
    return False


def _time_element_candidates(soup):
    """Yield DateResults from <time> elements, skipping untrustworthy ones.

    Two failure modes seen in production, both on House ASPX sites:

    1. The first <time> in document order belongs to a related-news rail
       rather than the article (see `_in_related_module`).
    2. The template hardcodes a constant `datetime` attribute — latta,
       hern and other documentsingle.aspx sites emit
       `datetime="2017-11-13"` on every <time> while the visible text
       carries the real date. An element that contradicts itself proves
       the attribute is a template constant, so neither half is trusted
       and the chain moves on to the body dateline.
    """
    for time_el in soup.select("time"):
        if _in_related_module(time_el):
            continue
        raw_attr = time_el.get("datetime")
        attr_dt = _parse_iso_datetime(raw_attr) if raw_attr else None
        text_res = parse_date_text(time_el.get_text(strip=True))

        if attr_dt and text_res and attr_dt.date() != text_res.value.date():
            continue

        if attr_dt:
            yield DateResult(value=attr_dt, source="time_element", confidence=0.90)
        elif text_res:
            text_res.source = "time_element"
            text_res.confidence = 0.85
            yield text_res


def _body_text_without_related(body) -> str:
    """Body text with related-content and nav modules stripped out.

    The body-text fallback reads the first 1000 characters, so a
    related-news rail rendered above the article would otherwise donate a
    neighbouring article's date. Walks the string nodes directly and skips
    those inside chrome, leaving the caller's soup untouched.
    """
    parts: list[str] = []
    total = 0
    for node in body.descendants:
        # Elements have a name; bare strings do not.
        if getattr(node, "name", None) is not None:
            continue
        text = str(node).strip()
        if not text or _in_related_module(node):
            continue
        parts.append(text)
        total += len(text) + 1
        if total > 1200:  # the caller only reads the first 1000 chars
            break
    return " ".join(parts)


def _html_date_candidates(soup):
    """Yield date candidates from `soup` in descending trust order."""
    # 1. OpenGraph / meta tags (highest confidence)
    # `datewritten` is the ColdFusion-stack convention used by Kennedy,
    # Thune, Cassidy and several other senate.gov ColdFusion sites.
    # Adding it lifts those senators from page_text/0.75 to meta_tag/0.95
    # without touching the heuristic chain.
    for attr in ["article:published_time", "og:article:published_time",
                 "datePublished", "date", "DC.date.issued", "pubdate",
                 "datewritten"]:
        meta = (soup.find("meta", property=attr)
                or soup.find("meta", attrs={"name": attr}))
        if meta and meta.get("content"):
            dt = _parse_iso_datetime(meta["content"])
            if dt:
                yield DateResult(value=dt, source="meta_tag", confidence=0.95)
                break

    # 2. JSON-LD
    for script in soup.select("script[type='application/ld+json']"):
        text = script.get_text()
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', text)
        if m:
            dt = _parse_iso_datetime(m.group(1))
            if dt:
                yield DateResult(value=dt, source="json_ld", confidence=0.95)
                break

    # 3-4. <time> elements, sidebar-filtered and self-consistency checked.
    yield from _time_element_candidates(soup)

    # 5. Date-like text in common CSS containers
    date_selectors = [
        ".date", ".post-date", ".entry-date", ".published",
        ".ArticleBlock__date", ".press-release-date",
        ".field-name-field-date", ".post-media-list-date",
        "span.datetime", ".recordListDate", ".pressDate",
    ]
    for sel in date_selectors:
        el = soup.select_one(sel)
        if el and not _in_related_module(el):
            result = parse_date_text(el.get_text(strip=True))
            if result:
                result.source = "css_selector"
                result.confidence = 0.80
                yield result
                break

    # 6. Fallback: date in first 1000 chars of body text
    # (ColdFusion sites like Graham have ~700 chars of nav before the date)
    body = soup.select_one("main") or soup.select_one("article") or soup.body
    if body:
        text = _body_text_without_related(body)[:1000]
        result = parse_date_text(text)
        if result:
            result.confidence = 0.50  # low confidence for body text extraction
            yield result


def extract_date_from_html(soup) -> DateResult | None:
    """Extract publication date from HTML using structured metadata.

    Tries in order: OpenGraph/meta tags, JSON-LD, <time> elements,
    common CSS date containers, then body text fallback.

    Returns the first candidate that passes `is_plausible_date`. If every
    candidate is implausible the best-ranked one is still returned so the
    row keeps a date and an audit trail — callers demote its confidence
    rather than losing the extraction entirely.

    Args:
        soup: BeautifulSoup object of the page.
    """
    fallback: DateResult | None = None
    for candidate in _html_date_candidates(soup):
        if is_plausible_date(candidate.value):
            return candidate
        if fallback is None:
            fallback = candidate
    return fallback


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


def demote_if_future(
    result: "DateResult | None",
    *,
    tolerance_days: int = 1,
    now: datetime | None = None,
) -> "DateResult | None":
    """Demote confidence and re-tag a DateResult that lands more than
    `tolerance_days` ahead of now. Senator press shops sometimes typo a
    month (e.g. "May 04" on a release scraped April 28); we keep the
    extracted date for journalistic provenance but downgrade confidence
    so downstream sorts and trust scores treat it as suspect. Returns the
    same DateResult mutated in place (or None if the input was None).
    """
    if result is None or result.value is None:
        return result
    reference = now or datetime.now(timezone.utc)
    val = result.value
    if val.tzinfo is None:
        val = val.replace(tzinfo=timezone.utc)
    delta_days = (val - reference).total_seconds() / 86400
    if delta_days > tolerance_days:
        # Keep the date and the original source for the audit trail; flag
        # the suspicion in the source string and crater confidence.
        result.source = f"{result.source}_future_typo"
        result.confidence = min(result.confidence, 0.2)
    return result
