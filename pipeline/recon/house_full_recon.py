"""
Comprehensive recon for US House members — Senate-parity coverage.

For each member in pipeline/seeds/house.json, this:

  1. Walks the member's official_url navigation for candidate content URLs
     matching channel keywords (news / media / press / op-ed / column /
     speech / statement / blog / newsletter / letter / weekly).
  2. Adds high-probability URL guesses from `senate.json` patterns:
     /media/press-releases, /news/press-releases, /media/columns, etc.
  3. For each candidate URL, fetches and classifies:
        - CMS family (drupal / wordpress / coldfusion / custom)
        - Listing-page yes/no (>=3 dated rows with detail links)
        - content_type from URL + nav text + page title
        - Listing selectors (list_item, title, date, detail_link)
        - Pagination shape (?page= / link-follow / load-more)
  4. Rejects blacklist URL patterns (photos, videos, art, in-the-news).
  5. Writes per-member channel inventory to:
        pipeline/recon/house_full_recon.json
        pipeline/recon/house_full_recon_report.md

Concurrency 3 + Chrome 130 headers (proven Akamai-safe in today's RSS
probe — 0 blocks across 437 members × 10 URL probes).

Usage:
    python pipeline/recon/house_full_recon.py
    python pipeline/recon/house_full_recon.py --limit 10           # first 10 only
    python pipeline/recon/house_full_recon.py --member begich-nicholas
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

SEED_FILE = ROOT / "pipeline" / "seeds" / "house.json"
OUT_JSON = ROOT / "pipeline" / "recon" / "house_full_recon.json"
OUT_REPORT = ROOT / "pipeline" / "recon" / "house_full_recon_report.md"

MAX_CONCURRENT = 3
REQUEST_TIMEOUT = 25.0

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not_A Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


# ---- Channel classification ----

# (regex on URL/text, content_type). First match wins. Patterns case-insensitive.
CHANNEL_KEYWORDS: list[tuple[str, str]] = [
    # press release first — beat the broader "news" capture
    (r"press[-\s]?release", "press_release"),
    (r"press[-\s]?statement", "statement"),
    (r"news[-\s]?release", "press_release"),
    # op-ed family
    (r"op[-\s]?ed", "op_ed"),
    (r"opinion", "op_ed"),
    (r"commentary", "op_ed"),
    (r"weekly[-\s]?column", "op_ed"),
    (r"\bcolumns?\b", "op_ed"),
    # speeches / floor
    (r"floor[-\s]?(speech|statement|remark)", "floor_statement"),
    (r"\bspeech(es)?\b", "floor_statement"),
    (r"\bremarks?\b", "floor_statement"),
    # statements (catch-all; runs after the press_release/floor specifics)
    (r"\bstatements?\b", "statement"),
    # blog / weekly recap
    (r"weekly[-\s]?recap", "blog"),
    (r"\bdiary\b", "blog"),
    (r"\bblogs?\b", "blog"),
    # letters
    (r"\bletters?[-\s]?to", "letter"),
    (r"oversight[-\s]?letter", "letter"),
    # newsletters (run last; loosest match)
    (r"e[-\s]?newsletter", "newsletter"),
    (r"\bnewsletters?\b", "newsletter"),
    (r"weekly[-\s]?(update|wrap|brief)", "newsletter"),
    # generic news / media (lowest priority — only if nothing more specific)
    (r"\bnewsroom\b", "press_release"),
    (r"\bmedia[-\s]?center\b", "press_release"),
]

# URL patterns to reject outright
BLACKLIST_PATTERNS = [
    r"/photos?(\b|/)",
    r"/photo[-\s]?gallery",
    r"/videos?(\b|/)",
    r"/gallery",
    r"/art[-\s]?(competition|submission)",
    r"/in[-\s]?the[-\s]?news",
    r"/in[-\s]?news",
    r"/press[-\s]?coverage",
    r"/media[-\s]?mentions?",
    r"/podcasts?(\b|/)",
    r"/audio(\b|/)",
    r"/contact",
    r"/about",
    r"/services",
    r"/biography",
    r"/legislat",  # legislation/bills pages, not press
    r"/issues?(\b|/)",
    r"/committees?(\b|/)",
    r"/internships?",
    r"/flag[-\s]?request",
    r"/grant",
    r"/intern",
    r"/sign[-\s]?up",
    r"/subscribe",
    r"\.pdf$",
    r"\.jpg$",
    r"\.png$",
]
BLACKLIST_RE = [re.compile(p, re.IGNORECASE) for p in BLACKLIST_PATTERNS]

# High-probability URL guesses to add even if nav doesn't link them.
URL_GUESSES = [
    "/media/press-releases",
    "/news/press-releases",
    "/press-releases",
    "/media/statements",
    "/news/statements",
    "/media/columns",
    "/news/columns",
    "/media/op-eds",
    "/news/op-eds",
    "/media/speeches",
    "/news/speeches",
    "/media/floor-speeches",
    "/news/floor-statements",
    "/media/e-newsletters",
    "/news/e-newsletters",
    "/media/newsletters",
    "/news/weekly-update",
    "/blog",
    "/news/blog",
    "/media/letters",
]


def classify_url(url: str, anchor_text: str = "") -> str | None:
    haystack = f"{url} {anchor_text}".lower()
    for pat, ct in CHANNEL_KEYWORDS:
        if re.search(pat, haystack, re.IGNORECASE):
            return ct
    return None


def is_blacklisted(url: str) -> bool:
    return any(rx.search(url) for rx in BLACKLIST_RE)


# ---- CMS / parser-family detection ----

def detect_cms(html: str, soup: BeautifulSoup) -> str:
    h = html[:8000].lower()
    if "wp-content" in h or "wp-json" in h:
        return "wordpress"
    meta_gen = soup.find("meta", attrs={"name": "generator"})
    if meta_gen:
        gc = str(meta_gen.get("content", "")).lower()
        if "wordpress" in gc:
            return "wordpress"
        if "drupal" in gc:
            return "drupal"
    if "drupal" in h or "data-drupal" in h:
        return "drupal"
    if soup.find(attrs={"class": re.compile(r"views-row|drupal", re.IGNORECASE)}):
        return "drupal"
    if "index.cfm" in h:
        return "coldfusion"
    return "custom"


# ---- Listing-page detection + selector extraction ----

DATE_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z\.]*\s+\d{1,2}[,\s]+20\d{2}\b"
    r"|\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b"
    r"|\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b",
    re.IGNORECASE,
)


def looks_like_listing(soup: BeautifulSoup) -> tuple[bool, dict]:
    """Heuristic: is this a press-release-style index?

    Looks for repeating structural blocks (>=3) where each contains an <a>
    pointing to a detail page and a parseable date nearby.

    Returns (is_listing, selector_hints).
    """
    candidates = [
        ".views-row",        # House Drupal default
        "article",
        "li.news-item",
        "li.press-release",
        ".news-item",
        ".press-release",
        ".release",
        ".post",
        "h2.title",
        "h3.title",
        "div.row",
    ]
    for sel in candidates:
        rows = soup.select(sel)
        if len(rows) < 3:
            continue
        # Need at least 3 rows with a link AND a parseable date in the row
        good = 0
        for r in rows:
            text = r.get_text(" ", strip=True)
            link = r.find("a", href=True)
            if link and DATE_RE.search(text):
                good += 1
            if good >= 3:
                break
        if good >= 3:
            # Try to find tighter title/date subselectors
            sample = rows[0]
            title_link = sample.find("a", href=True)
            title_sel = None
            if title_link:
                # If title link is inside h2/h3, that's a strong signal
                parent_heading = title_link.find_parent(["h1", "h2", "h3", "h4"])
                if parent_heading:
                    title_sel = f"{parent_heading.name} a"
                else:
                    title_sel = "a"
            return True, {
                "list_item": sel,
                "title": title_sel,
                "date": None,
                "detail_link": "a[href]",
            }
    return False, {}


# ---- Pagination detection ----

def detect_pagination(soup: BeautifulSoup, base_url: str) -> dict | None:
    # Drupal: ?page=1, ?page=2 ...
    page_link = soup.find("a", href=re.compile(r"[?&]page=\d+"))
    if page_link:
        return {"type": "query_param", "param": "page", "starts_at": 0}
    # Senate-generic .pager-next or rel=next
    rel_next = soup.find("a", attrs={"rel": "next"})
    if rel_next:
        return {"type": "link_follow", "next_selector": 'a[rel="next"]'}
    pager = soup.find("a", class_=re.compile(r"pager-next|next-page|pagination-next", re.IGNORECASE))
    if pager:
        return {"type": "link_follow", "next_selector": "a.pager-next, a.next-page, a.pagination-next"}
    text_next = soup.find("a", string=re.compile(r"^\s*(next|older)\b", re.IGNORECASE))
    if text_next:
        return {"type": "link_follow", "next_selector": "a.next, a.older"}
    return None


# ---- Data classes ----

@dataclass
class ChannelProbe:
    url: str
    discovered_via: str  # "nav" / "guess" / "rss_feed_url"
    status_code: int | None = None
    is_listing: bool = False
    cms: str = ""
    content_type: str | None = None
    selectors: dict = field(default_factory=dict)
    pagination: dict | None = None
    item_count_seen: int = 0
    nav_anchor_text: str = ""
    rejected: str | None = None     # populated if we drop the channel
    error: str = ""


@dataclass
class MemberRecon:
    member_id: str
    full_name: str
    state: str
    party: str
    district: str | int | None
    parser_family: str
    official_url: str
    nav_links_seen: int = 0
    channels: list[ChannelProbe] = field(default_factory=list)
    cms_family: str = ""
    error: str = ""


# ---- Probe logic ----

async def fetch(client: httpx.AsyncClient, url: str) -> tuple[int | None, str, str]:
    """Returns (status_code, content_type_header, body_text)."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=REQUEST_TIMEOUT)
        return resp.status_code, resp.headers.get("content-type", ""), resp.text
    except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
        return None, "", f"__error__:{type(e).__name__}: {e}"
    except Exception as e:
        return None, "", f"__error__:{type(e).__name__}: {e}"


def find_nav_candidates(home_html: str, base_url: str) -> list[tuple[str, str]]:
    """Return [(absolute_url, anchor_text)] for candidate channel links."""
    soup = BeautifulSoup(home_html, "lxml")
    out: list[tuple[str, str]] = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        anchor_text = a.get_text(" ", strip=True)[:80]
        absolute = urljoin(base_url, href)
        # Same-host only
        try:
            base_host = urlparse(base_url).netloc
            link_host = urlparse(absolute).netloc
        except Exception:
            continue
        if link_host and base_host and link_host != base_host:
            continue
        if classify_url(absolute, anchor_text) is None:
            continue
        if is_blacklisted(absolute):
            continue
        # Strip fragments / trailing slashes for dedup
        norm = absolute.split("#", 1)[0].rstrip("/")
        if norm in seen:
            continue
        seen.add(norm)
        out.append((norm, anchor_text))
    return out


async def probe_channel(
    client: httpx.AsyncClient,
    url: str,
    discovered_via: str,
    anchor_text: str,
) -> ChannelProbe:
    rec = ChannelProbe(url=url, discovered_via=discovered_via, nav_anchor_text=anchor_text)
    if is_blacklisted(url):
        rec.rejected = "blacklist"
        return rec
    status, ctype, body = await fetch(client, url)
    rec.status_code = status
    if body.startswith("__error__:"):
        rec.error = body[len("__error__:"):]
        return rec
    if status != 200:
        return rec
    if "html" not in ctype.lower() and "<html" not in body[:200].lower():
        return rec
    soup = BeautifulSoup(body, "lxml")
    rec.cms = detect_cms(body, soup)
    is_listing, sels = looks_like_listing(soup)
    rec.is_listing = is_listing
    if is_listing:
        rec.selectors = sels
        rec.pagination = detect_pagination(soup, url)
        # rough item count
        rec.item_count_seen = len(soup.select(sels.get("list_item", ""))) if sels else 0
    # Classify content_type from URL + page <title> + nav anchor
    page_title = soup.title.get_text(strip=True) if soup.title else ""
    rec.content_type = classify_url(url, f"{anchor_text} {page_title}")
    return rec


async def probe_member(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    member: dict,
) -> MemberRecon:
    async with sem:
        mid = member["member_id"]
        official = (member.get("official_url") or "").rstrip("/")
        result = MemberRecon(
            member_id=mid,
            full_name=member.get("full_name", ""),
            state=member.get("state", ""),
            party=member.get("party", ""),
            district=member.get("district"),
            parser_family=member.get("parser_family", ""),
            official_url=official,
        )
        if not official:
            result.error = "no official_url"
            return result

        t0 = time.monotonic()

        # Step 1: fetch homepage, harvest nav-driven candidates
        status, ctype, body = await fetch(client, official + "/")
        if status != 200 or body.startswith("__error__:"):
            # Try without trailing slash
            status, ctype, body = await fetch(client, official)
        if status == 200 and not body.startswith("__error__:"):
            soup = BeautifulSoup(body, "lxml")
            result.cms_family = detect_cms(body, soup)
            nav_candidates = find_nav_candidates(body, official)
            result.nav_links_seen = len(nav_candidates)
        else:
            result.cms_family = "unreachable"
            nav_candidates = []
            if body.startswith("__error__:"):
                result.error = body[len("__error__:"):]

        # Step 2: union with high-probability URL guesses
        guess_candidates = [(official + p, "") for p in URL_GUESSES]

        # Dedup on URL
        all_candidates: dict[str, tuple[str, str]] = {}
        for u, anchor in nav_candidates:
            all_candidates.setdefault(u, ("nav", anchor))
        for u, anchor in guess_candidates:
            all_candidates.setdefault(u, ("guess", anchor))

        # Step 3: probe each candidate, throttled politely
        for url, (via, anchor) in all_candidates.items():
            ch = await probe_channel(client, url, via, anchor)
            result.channels.append(ch)
            await asyncio.sleep(0.12)

        elapsed = time.monotonic() - t0
        listing_count = sum(
            1 for c in result.channels if c.is_listing and not c.rejected
        )
        print(
            f"  {mid:<32} cms={result.cms_family:<10} nav={result.nav_links_seen:>2} "
            f"channels={len(result.channels):>3} listings={listing_count:>2} ({elapsed:.1f}s)",
            flush=True,
        )
        return result


async def run(limit: int | None = None, only_member: str | None = None):
    seed = json.loads(SEED_FILE.read_text())
    members = seed["members"]
    if only_member:
        members = [m for m in members if m["member_id"] == only_member]
    if limit:
        members = members[:limit]
    print(
        f"Comprehensive recon: {len(members)} House member(s), "
        f"concurrency={MAX_CONCURRENT}"
    )

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    async with httpx.AsyncClient(
        headers=BROWSER_HEADERS,
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
        follow_redirects=True,
    ) as client:
        tasks = [probe_member(client, sem, m) for m in members]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    clean: list[MemberRecon] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            mid = members[i]["member_id"]
            print(f"  [X] {mid}: {type(r).__name__}: {r}")
            clean.append(MemberRecon(
                member_id=mid,
                full_name=members[i].get("full_name", ""),
                state=members[i].get("state", ""),
                party=members[i].get("party", ""),
                district=members[i].get("district"),
                parser_family=members[i].get("parser_family", ""),
                official_url=members[i].get("official_url", ""),
                error=f"{type(r).__name__}: {r}",
            ))
        else:
            clean.append(r)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "concurrency": MAX_CONCURRENT,
                "url_guesses": URL_GUESSES,
                "channel_keywords": [(p, ct) for p, ct in CHANNEL_KEYWORDS],
                "blacklist_patterns": BLACKLIST_PATTERNS,
                "results": [asdict(r) for r in clean],
            },
            f,
            indent=2,
            default=str,
        )

    report = generate_report(clean)
    OUT_REPORT.write_text(report)

    print()
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_REPORT}")


def generate_report(results: list[MemberRecon]) -> str:
    total = len(results)
    cms_counts = Counter(r.cms_family for r in results)

    listing_counts: Counter[str] = Counter()
    for r in results:
        for c in r.channels:
            if c.is_listing and not c.rejected and c.content_type:
                listing_counts[c.content_type] += 1

    members_with_press_release = sum(
        1
        for r in results
        if any(
            c.is_listing and c.content_type == "press_release" and not c.rejected
            for c in r.channels
        )
    )
    members_with_zero_listings = sum(
        1
        for r in results
        if not any(c.is_listing and not c.rejected for c in r.channels)
    )

    lines: list[str] = []
    lines.append("# House Comprehensive Recon Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Members probed:** {total}")
    lines.append(f"**Concurrency:** {MAX_CONCURRENT}")
    lines.append("")
    lines.append("## Topline")
    lines.append("")
    lines.append(
        f"- Members with a working press_release listing: "
        f"**{members_with_press_release} / {total}**"
    )
    lines.append(
        f"- Members with zero working listings (likely blocked or non-standard): "
        f"**{members_with_zero_listings}**"
    )
    lines.append(
        f"- Total listings detected across content types: **{sum(listing_counts.values())}**"
    )
    lines.append("")
    lines.append("## CMS family distribution")
    lines.append("")
    lines.append("| Family | Members |")
    lines.append("|---|---:|")
    for fam, n in cms_counts.most_common():
        lines.append(f"| {fam} | {n} |")
    lines.append("")
    lines.append("## Listings detected by content_type")
    lines.append("")
    lines.append("| content_type | Count |")
    lines.append("|---|---:|")
    for ct, n in listing_counts.most_common():
        lines.append(f"| {ct} | {n} |")
    lines.append("")
    lines.append("## Per-member channel summary (first 50)")
    lines.append("")
    lines.append("| Member | State | District | CMS | Channels | Listings | Press? | Op-Ed? | Speech? | Newsletter? |")
    lines.append("|---|---|---|---|---:|---:|:-:|:-:|:-:|:-:|")
    for r in sorted(results, key=lambda x: (x.state, str(x.district), x.member_id))[:50]:
        listings = [c for c in r.channels if c.is_listing and not c.rejected]
        types = {c.content_type for c in listings if c.content_type}
        lines.append(
            f"| {r.full_name} | {r.state} | {r.district} | {r.cms_family} | "
            f"{len(r.channels)} | {len(listings)} | "
            f"{'Y' if 'press_release' in types else ''} | "
            f"{'Y' if 'op_ed' in types else ''} | "
            f"{'Y' if 'floor_statement' in types else ''} | "
            f"{'Y' if 'newsletter' in types else ''} |"
        )
    lines.append("")
    lines.append("Full per-member detail in `house_full_recon.json`.")
    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Comprehensive House recon")
    parser.add_argument("--limit", type=int, help="Probe only the first N members")
    parser.add_argument("--member", help="Probe only one member by member_id")
    args = parser.parse_args()
    asyncio.run(run(limit=args.limit, only_member=args.member))


if __name__ == "__main__":
    main()
