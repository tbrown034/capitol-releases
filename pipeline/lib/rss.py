"""
RSS feed discovery and parsing for Capitol Releases.

RSS is the most reliable collection method: no selectors to break,
structured dates, often includes full content. For WordPress senators
(47 of 100), RSS feeds are almost always available at predictable URLs.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx
from bs4 import BeautifulSoup

from pipeline.lib.http import create_client, HEADERS

log = logging.getLogger("capitol.rss")

# URL patterns to probe for RSS feeds, in order of preference.
# Narrow feeds (press-releases-only) are preferred over broad site feeds.
_FEED_PROBE_PATTERNS = [
    "{press_url}/feed/",
    "{press_url}/feed",
    "{press_url}feed/",
    "{base}/feed/",
    "{base}/news/press-releases/feed/",
    "{base}/newsroom/press-releases/feed/",
    "{base}/press-releases/feed/",
    "{base}/category/press-releases/feed/",
    "{base}/category/press-release/feed/",
    "{base}/category/press_release/feed/",
    "{base}/news/feed/",
    "{base}/newsroom/feed/",
    "{base}/rss/",
    "{base}/rss",
]


@dataclass
class FeedItem:
    """A single item from an RSS feed."""
    title: str
    url: str
    published_at: datetime | None
    summary: str = ""
    categories: list[str] = field(default_factory=list)


@dataclass
class FeedDiscoveryResult:
    """Result of probing a senator's site for RSS feeds."""
    senator_id: str
    feed_url: str | None
    feed_type: str = ""        # rss, atom, or empty
    item_count: int = 0
    is_narrow: bool = False    # True if feed is press-release-specific
    probe_method: str = ""     # url_probe, link_tag, or empty
    error: str = ""


def _looks_like_feed(content_type: str, body: str) -> str:
    """Check if a response looks like an RSS or Atom feed. Returns type or empty string."""
    ct = content_type.lower()
    if "xml" in ct or "rss" in ct or "atom" in ct:
        if "<rss" in body[:500]:
            return "rss"
        if "<feed" in body[:500]:
            return "atom"
        if "<?xml" in body[:200]:
            return "rss"  # assume RSS for generic XML
    # Content-type might be text/html but body is actually XML
    if body.lstrip().startswith("<?xml") or "<rss" in body[:500] or "<feed" in body[:500]:
        if "<rss" in body[:500]:
            return "rss"
        if "<feed" in body[:500]:
            return "atom"
    return ""


# ColdFusion RSS feeds on Boozman/Kennedy/Moran emit day-of-year where the
# RFC 2822 day-of-month field should be, e.g. "Thu, 113 Apr 2026 12:00:00 EST".
# Detect values 32-366 in the DD slot and rebuild the date from the year + DOY.
_DOY_PATTERN = re.compile(
    r"^\s*(?:[A-Za-z]{3},\s+)?"
    r"(\d{1,3})\s+"
    r"[A-Za-z]{3}\s+"
    r"(\d{4})\s+"
    r"(\d{2}):(\d{2}):(\d{2})"
    r"(?:\s+[A-Za-z0-9+\-:]{1,6})?\s*$"
)


def _parse_rss_date(date_str: str) -> datetime | None:
    """Parse an RSS pubDate or Atom updated/published date."""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        pass
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, TypeError):
        pass
    m = _DOY_PATTERN.match(date_str)
    if m:
        doy, year, hh, mm, ss = (int(x) for x in m.groups())
        if 32 <= doy <= 366:
            try:
                d = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy - 1)
                return d.replace(hour=hh, minute=mm, second=ss)
            except (ValueError, OverflowError):
                pass
    return None


def parse_feed_items(xml_text: str) -> list[FeedItem]:
    """Parse RSS/Atom XML into FeedItem objects.

    Uses BeautifulSoup for robustness against malformed feeds
    (which is common on government sites).
    """
    soup = BeautifulSoup(xml_text, "lxml-xml")
    items: list[FeedItem] = []

    # Try RSS <item> elements first
    for item in soup.find_all("item"):
        title = (item.find("title") or item).get_text(strip=True)
        link_el = item.find("link")
        link = ""
        if link_el:
            link = link_el.get_text(strip=True) or link_el.get("href", "")

        pub_el = item.find("pubDate") or item.find("pubdate")
        pub_date = _parse_rss_date(pub_el.get_text(strip=True) if pub_el else "")

        desc_el = item.find("description") or item.find("content:encoded")
        summary = desc_el.get_text(strip=True)[:500] if desc_el else ""

        cats = [c.get_text(strip=True) for c in item.find_all("category")]

        if title and link:
            items.append(FeedItem(
                title=title, url=link, published_at=pub_date,
                summary=summary, categories=cats,
            ))

    if items:
        return items

    # Try Atom <entry> elements
    for entry in soup.find_all("entry"):
        title = (entry.find("title") or entry).get_text(strip=True)
        link_el = entry.find("link")
        link = link_el.get("href", "") if link_el else ""

        pub_el = entry.find("published") or entry.find("updated")
        pub_date = _parse_rss_date(pub_el.get_text(strip=True) if pub_el else "")

        summary_el = entry.find("summary") or entry.find("content")
        summary = summary_el.get_text(strip=True)[:500] if summary_el else ""

        if title and link:
            items.append(FeedItem(
                title=title, url=link, published_at=pub_date,
                summary=summary, categories=[],
            ))

    return items


async def discover_feed(
    client: httpx.AsyncClient,
    senator_id: str,
    press_release_url: str,
    official_url: str,
) -> FeedDiscoveryResult:
    """Probe a senator's site for RSS feeds.

    Tries URL patterns first, then checks for <link rel="alternate"> tags
    on the press release page.
    """
    base = official_url.rstrip("/")
    press_url = press_release_url.rstrip("/")

    # 1. Probe URL patterns
    for pattern in _FEED_PROBE_PATTERNS:
        url = pattern.format(base=base, press_url=press_url)
        try:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code == 200:
                feed_type = _looks_like_feed(
                    resp.headers.get("content-type", ""), resp.text
                )
                if feed_type:
                    items = parse_feed_items(resp.text)
                    is_narrow = "press" in url.lower()
                    log.info(
                        "RSS found for %s: %s (%d items, %s)",
                        senator_id, url, len(items),
                        "narrow" if is_narrow else "broad",
                    )
                    return FeedDiscoveryResult(
                        senator_id=senator_id,
                        feed_url=str(resp.url),  # use final URL after redirects
                        feed_type=feed_type,
                        item_count=len(items),
                        is_narrow=is_narrow,
                        probe_method="url_probe",
                    )
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            log.debug("Probe timeout for %s at %s: %s", senator_id, url, e)
            continue
        except Exception as e:
            log.debug("Probe error for %s at %s: %s", senator_id, url, e)
            continue

    # 2. Check <link rel="alternate"> on the press release page
    try:
        resp = await client.get(press_release_url, follow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            for link in soup.find_all("link", rel="alternate"):
                link_type = (link.get("type") or "").lower()
                if "rss" in link_type or "atom" in link_type or "xml" in link_type:
                    feed_href = link.get("href", "")
                    if feed_href:
                        # Resolve relative URLs
                        if feed_href.startswith("/"):
                            feed_href = f"{base}{feed_href}"
                        # Verify the feed works
                        try:
                            feed_resp = await client.get(feed_href, follow_redirects=True)
                            if feed_resp.status_code == 200:
                                feed_type = _looks_like_feed(
                                    feed_resp.headers.get("content-type", ""),
                                    feed_resp.text,
                                )
                                if feed_type:
                                    items = parse_feed_items(feed_resp.text)
                                    log.info(
                                        "RSS found via link tag for %s: %s (%d items)",
                                        senator_id, feed_href, len(items),
                                    )
                                    return FeedDiscoveryResult(
                                        senator_id=senator_id,
                                        feed_url=str(feed_resp.url),
                                        feed_type=feed_type,
                                        item_count=len(items),
                                        is_narrow="press" in feed_href.lower(),
                                        probe_method="link_tag",
                                    )
                        except Exception:
                            continue
    except Exception as e:
        log.debug("Link tag check failed for %s: %s", senator_id, e)

    return FeedDiscoveryResult(senator_id=senator_id, feed_url=None)


async def discover_all_feeds(
    senators: list[dict],
    max_concurrent: int = 8,
) -> list[FeedDiscoveryResult]:
    """Discover RSS feeds for all senators concurrently."""
    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[FeedDiscoveryResult] = []

    async def probe_one(client, senator):
        async with semaphore:
            result = await discover_feed(
                client,
                senator["senator_id"],
                senator.get("press_release_url", ""),
                senator.get("official_url", ""),
            )
            results.append(result)
            await asyncio.sleep(0.5)  # politeness

    async with create_client(timeout=15.0) as client:
        tasks = [probe_one(client, s) for s in senators]
        await asyncio.gather(*tasks, return_exceptions=True)

    return results
