"""
Recon for House members where the original recon couldn't auto-detect a
press-release listing (collection_method is null in pipeline/seeds/house.json).

Strategy beyond the original heuristic:

  1. Try a wider URL-guess set (ASP.NET DocumentQuery, /press, /press-center,
     /newsroom, /press_releases, /category/news/press-release/, etc).
  2. Walk the homepage nav for press-release-ish anchors.
  3. After fetching each candidate, run the original heuristic AND a
     "common-link-pattern" detector that finds repeating detail-page URL
     shapes (e.g. /press-releases?id=<GUID>, /news/<slug>, /?p=NNNN). When
     5+ such links share a parent container class, that container becomes
     the list_item selector.
  4. Also test selectors the original missed: .ContentBlock, .blog-entry,
     .news-listing-item, .pr-list-item, td.news, etc.
  5. Verify by extracting 5+ items per detected selector with a >=15-char
     headline and a real <a href>.

Writes pipeline/recon/house_unconfigured_discoveries.json.

Usage:
    python pipeline/recon/house_unconfigured_recon.py
    python pipeline/recon/house_unconfigured_recon.py --member sewell-terri
    python pipeline/recon/house_unconfigured_recon.py --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent.parent
SEED_FILE = ROOT / "pipeline" / "seeds" / "house.json"
OUT_JSON = ROOT / "pipeline" / "recon" / "house_unconfigured_discoveries.json"

MAX_CONCURRENT = 3
REQUEST_TIMEOUT = 25.0
POLITE_DELAY = 0.20  # seconds between requests on same host

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

DATE_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z\.]*\s+\d{1,2}[,\s]+20\d{2}\b"
    r"|\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b"
    r"|\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2}|\d{2})\b",
    re.IGNORECASE,
)

# URL-path guesses to try beyond the original recon.
URL_GUESSES = [
    "/press-releases",
    "/press-releases/",
    "/media/press-releases",
    "/media/press-releases/",
    "/media-center/press-releases",
    "/media-center/press-releases/",
    "/newsroom/press-releases",
    "/newsroom/press-releases/",
    "/news/press-releases",
    "/news/press-releases/",
    "/category/press-releases/",
    "/category/press-release/",
    "/category/press_release/",
    "/category/press_releases/",
    "/category/congress_press_release/",
    "/category/news/",
    "/news",
    "/news/",
    "/press",
    "/press/",
    "/newsroom",
    "/newsroom/",
    "/media",
    "/media/",
    "/press-center",
    "/press-center/",
    "/in-the-press",
    "/press-room",
    "/press_releases",
    "/news/documentquery.aspx?DocumentTypeID=27",
    "/news/DocumentQuery.aspx?DocumentTypeID=27",
    "/news/documentquery.aspx?DocumentTypeID=1",
    "/news/documentquery.aspx?DocumentTypeID=657",
    "/news/documentquery.aspx",
    "/News/DocumentQuery.aspx?DocumentTypeID=27",
    "/news/documentsingle.aspx?DocumentTypeID=27",
    "/Newsroom",
    "/Press-Releases",
    "/news/documentquery.aspx?DocumentTypeID=2402",
]

# Press-release-ish nav anchor regex
NAV_PRESS_RE = re.compile(
    r"press[-\s]?releases?|press[-\s]?room|press[-\s]?center|"
    r"newsroom|news[-\s]?releases?|in[-\s]the[-\s]news|"
    r"^news$|^news\b|media[-\s]center|media[-\s]room|^media$|statements?",
    re.IGNORECASE,
)

# Listing-row selectors. Ordered most-specific to least-specific.
SELECTOR_CANDIDATES = [
    # Drupal House
    ".views-row",
    ".view-content > .views-row",
    # ASP.NET / "DocumentQuery" House
    ".ContentBlock",
    ".recordList tr",
    ".news_record",
    "tr.news",
    # Generic press list patterns
    ".news-item",
    ".press-release",
    ".pr-list-item",
    ".news-listing-item",
    "li.news-item",
    "li.press-release",
    "li.has-bg",
    "li.list-item",
    "li.listing-item",
    "div.news-item",
    "div.press-release",
    "div.list-item",
    "div.listing-item",
    "div.archive-item",
    "div.archive-card",
    "div.media-item",
    "div.cards-list > div",
    "div.row.news",
    # WordPress-ish
    "article",
    "article.hentry",
    "article.post",
    "article.type-post",
    "li.post-item",
    "div.post-item",
    "div.post",
    ".post",
    ".entry",
    ".entry-content > article",
    # Generic
    ".item",
    ".loop-item",
    ".card",
    ".result",
    ".release",
    "main article",
    # Fallback
    "li",
    "tr",
]

# URL/path shapes a press-release detail link tends to take.
DETAIL_LINK_SHAPES = [
    re.compile(r"/press[-_]releases?/[^/?#]+/?$", re.IGNORECASE),
    re.compile(r"/news/[^/?#]+/?$", re.IGNORECASE),
    re.compile(r"\?(?:doc(?:ument)?id|documentid|id)=", re.IGNORECASE),
    re.compile(r"DocumentSingle\.aspx", re.IGNORECASE),
    re.compile(r"/\?p=\d+"),
    re.compile(r"/20\d\d/\d\d/", re.IGNORECASE),
    re.compile(r"/category/.+/[^/?#]+/?$", re.IGNORECASE),
]


async def fetch(client: httpx.AsyncClient, url: str) -> tuple[int | None, str, str, str]:
    """Returns (status_code, content_type_header, body_text, final_url)."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=REQUEST_TIMEOUT)
        return (
            resp.status_code,
            resp.headers.get("content-type", ""),
            resp.text,
            str(resp.url),
        )
    except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
        return None, "", f"__error__:{type(e).__name__}: {e}", url
    except Exception as e:
        return None, "", f"__error__:{type(e).__name__}: {e}", url


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
    if "documentquery.aspx" in h or "documentsingle.aspx" in h:
        return "aspnet-house"
    if "index.cfm" in h:
        return "coldfusion"
    return "custom"


def parser_family_from_cms(cms: str) -> str:
    if cms == "drupal":
        return "senate-drupal"
    if cms == "wordpress":
        return "senate-wordpress"
    if cms == "aspnet-house":
        return "senate-generic"
    return "senate-generic"


def _row_link(row) -> object | None:
    """Return an <a href> for a row whether the row IS an anchor or contains one."""
    if getattr(row, "name", None) == "a" and row.get("href"):
        return row
    return row.find("a", href=True)


def looks_like_listing_classic(soup: BeautifulSoup) -> tuple[str | None, dict]:
    """Original heuristic: class-based selector + >=3 dated rows w/ links."""
    for sel in SELECTOR_CANDIDATES:
        try:
            rows = soup.select(sel)
        except Exception:
            continue
        if len(rows) < 3:
            continue
        # need 3 rows with link AND parseable date in the row
        good = 0
        for r in rows:
            text = r.get_text(" ", strip=True)
            link = _row_link(r)
            if link and len(text) > 30 and DATE_RE.search(text):
                good += 1
            if good >= 3:
                break
        if good >= 3:
            return sel, _selectors_for(rows[0], sel)
    return None, {}


def _selectors_for(sample, list_sel: str) -> dict:
    # If the row itself is an <a>, the title likely lives in an <hN> child.
    if getattr(sample, "name", None) == "a" and sample.get("href"):
        # Self-anchored row. Title is a heading inside, or the anchor itself.
        heading = sample.find(["h1", "h2", "h3", "h4"])
        title_sel = heading.name if heading else None
        return {
            "list_item": list_sel,
            "title": title_sel,
            "date": None,
            "detail_link": None,  # the row itself is the link
        }
    title_link = sample.find("a", href=True)
    title_sel = None
    if title_link:
        parent_heading = title_link.find_parent(["h1", "h2", "h3", "h4"])
        if parent_heading:
            title_sel = f"{parent_heading.name} a"
        else:
            title_sel = "a"
    # Try to find a date sub-element
    date_sel = None
    for cls in ("date", "post-date", "entry-date", "news-date", "published", "time"):
        n = sample.find(class_=re.compile(cls, re.IGNORECASE))
        if n:
            date_sel = f".{n.get('class')[0]}" if n.get("class") else None
            break
    if not date_sel:
        t = sample.find("time")
        if t:
            date_sel = "time"
    return {
        "list_item": list_sel,
        "title": title_sel or "a",
        "date": date_sel,
        "detail_link": "a[href]",
    }


def looks_like_listing_by_link_pattern(
    soup: BeautifulSoup, page_url: str
) -> tuple[str | None, dict, list[str]]:
    """
    Fallback: find 5+ <a> whose href matches a press-release detail shape, all
    sharing a common parent container's class. Use that container as list_item.
    """
    base_host = urlparse(page_url).netloc
    matches: list[tuple[BeautifulSoup, str, str]] = []  # (anchor, href, text)
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(page_url, href)
        try:
            link_host = urlparse(absolute).netloc
        except Exception:
            continue
        if link_host and base_host and link_host != base_host:
            continue
        if not any(rx.search(absolute) for rx in DETAIL_LINK_SHAPES):
            continue
        text = a.get_text(" ", strip=True)
        if len(text) < 15:
            continue
        matches.append((a, absolute, text))

    if len(matches) < 5:
        return None, {}, []

    # Find common ancestor — try (tag, class) first, then bare tag if no class.
    container_class_counts: Counter = Counter()
    container_tag_counts: Counter = Counter()
    # For tag-only signal, pick the *closest* repeating block-tag (li, tr,
    # article, div). We collect all ancestor tags to find a tight wrapper.
    BLOCK_TAGS = {"tr", "li", "article", "div"}
    for a, _, _ in matches:
        node = a.parent
        depth = 0
        found_class = False
        # First repeating tag-only ancestor
        first_block_tag: tuple[str, BeautifulSoup] | None = None
        while node is not None and depth < 8:
            cls = node.get("class") if hasattr(node, "get") else None
            if cls and not found_class:
                container_class_counts[(node.name, cls[0])] += 1
                found_class = True
            if (
                first_block_tag is None
                and getattr(node, "name", None) in BLOCK_TAGS
            ):
                first_block_tag = (node.name, node)
                container_tag_counts[node.name] += 1
            node = getattr(node, "parent", None)
            depth += 1

    selector: str | None = None
    if container_class_counts:
        (tag, klass), count = container_class_counts.most_common(1)[0]
        if count >= 5:
            selector = f"{tag}.{klass}"

    if not selector and container_tag_counts:
        # Tag-only fallback (e.g. tr / li under recordsContainer). Try to
        # tighten by combining with a nearby ancestor that has a class.
        tag, count = container_tag_counts.most_common(1)[0]
        if count >= 5:
            # Look for an ancestor with a class to scope the bare tag.
            # Take the most common (ancestor_class, ancestor_tag) seen for
            # rows whose closest block-tag is `tag`.
            scope_counts: Counter = Counter()
            for a, _, _ in matches:
                node = a.parent
                depth = 0
                hit_block = False
                while node is not None and depth < 10:
                    if not hit_block and getattr(node, "name", None) == tag:
                        hit_block = True
                    elif hit_block:
                        cls = node.get("class") if hasattr(node, "get") else None
                        if cls:
                            scope_counts[(node.name, cls[0])] += 1
                            break
                    node = getattr(node, "parent", None)
                    depth += 1
            if scope_counts:
                (stag, sclass), scount = scope_counts.most_common(1)[0]
                if scount >= 5:
                    candidate = f"{stag}.{sclass} {tag}"
                    try:
                        rows = soup.select(candidate)
                        if len(rows) >= 5:
                            selector = candidate
                    except Exception:
                        pass
            if not selector:
                selector = tag

    if not selector:
        return None, {}, []

    try:
        rows = soup.select(selector)
    except Exception:
        return None, {}, []
    if len(rows) < 5:
        return None, {}, []

    # Verify each row has an <a href> matching DETAIL_LINK_SHAPES + >=15-char text.
    sample_titles: list[str] = []
    good = 0
    good_rows: list = []
    for r in rows:
        candidate_link = None
        for a in r.find_all("a", href=True):
            href = a["href"].strip()
            absolute = urljoin(page_url, href)
            try:
                link_host = urlparse(absolute).netloc
            except Exception:
                continue
            if link_host and base_host and link_host != base_host:
                continue
            if not any(rx.search(absolute) for rx in DETAIL_LINK_SHAPES):
                continue
            text = a.get_text(" ", strip=True)
            if len(text) >= 15:
                candidate_link = a
                break
        if not candidate_link:
            continue
        good += 1
        good_rows.append(r)
        if len(sample_titles) < 5:
            sample_titles.append(candidate_link.get_text(" ", strip=True)[:120])
    if good < 5:
        return None, {}, []

    sels = _selectors_for(good_rows[0], selector)
    return selector, sels, sample_titles


def detect_pagination(soup: BeautifulSoup) -> dict | None:
    page_link = soup.find("a", href=re.compile(r"[?&]page=\d+"))
    if page_link:
        return {"type": "query_param", "param": "page", "starts_at": 0}
    paged_link = soup.find("a", href=re.compile(r"[?&]paged=\d+"))
    if paged_link:
        return {"type": "query_param", "param": "paged", "starts_at": 1}
    rel_next = soup.find("a", attrs={"rel": "next"})
    if rel_next:
        return {"type": "link_follow", "next_selector": 'a[rel="next"]'}
    pager = soup.find(
        "a",
        class_=re.compile(r"pager-next|next-page|pagination-next|pager__next", re.IGNORECASE),
    )
    if pager:
        return {
            "type": "link_follow",
            "next_selector": "a.pager-next, a.next-page, a.pagination-next, a.pager__next",
        }
    text_next = soup.find("a", string=re.compile(r"^\s*(next|older)\b", re.IGNORECASE))
    if text_next:
        return {"type": "link_follow", "next_selector": "a.next, a.older"}
    return None


def find_press_nav_links(home_html: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(home_html, "lxml")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        anchor_text = a.get_text(" ", strip=True)[:80]
        if not anchor_text and not a.get("aria-label"):
            continue
        haystack = f"{href} {anchor_text} {a.get('aria-label', '')}"
        if not NAV_PRESS_RE.search(haystack):
            continue
        absolute = urljoin(base_url, href)
        try:
            base_host = urlparse(base_url).netloc
            link_host = urlparse(absolute).netloc
        except Exception:
            continue
        if link_host and base_host and link_host != base_host:
            continue
        norm = absolute.split("#", 1)[0].rstrip("/")
        if norm in seen:
            continue
        seen.add(norm)
        out.append((absolute, anchor_text))
    return out


async def probe_member(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    member: dict,
) -> dict:
    """Returns a dict with either 'discovery' or 'still_broken' fields."""
    async with sem:
        mid = member["member_id"]
        official = (member.get("official_url") or "").rstrip("/")
        if not official:
            return {
                "member_id": mid,
                "still_broken": True,
                "tried_urls": [],
                "reason": "no official_url",
            }

        seed_press_url = (member.get("press_release_url") or "").rstrip("/")

        t0 = time.monotonic()

        # Step 1: fetch homepage to harvest nav-driven candidates.
        nav_candidates: list[tuple[str, str]] = []
        home_status, home_ctype, home_body, home_final = await fetch(client, official + "/")
        if home_status != 200 or home_body.startswith("__error__:"):
            home_status, home_ctype, home_body, home_final = await fetch(client, official)
        if home_status == 200 and not home_body.startswith("__error__:"):
            nav_candidates = find_press_nav_links(home_body, official)
        await asyncio.sleep(POLITE_DELAY)

        # Step 2: build candidate URL list.
        all_candidates: list[tuple[str, str]] = []
        seen_urls: set[str] = set()

        def add(url: str, source: str) -> None:
            n = url.rstrip("/").split("#", 1)[0]
            if n in seen_urls:
                return
            seen_urls.add(n)
            all_candidates.append((url, source))

        if seed_press_url:
            add(seed_press_url, "seed")
        for u, _ in nav_candidates:
            add(u, "nav")
        for path in URL_GUESSES:
            add(official + path, "guess")

        # Step 3: probe each candidate.
        tried: list[dict] = []
        best: dict | None = None
        for url, source in all_candidates:
            status, ctype, body, final = await fetch(client, url)
            await asyncio.sleep(POLITE_DELAY)
            entry = {
                "url": url,
                "final_url": final,
                "source": source,
                "status": status,
            }
            tried.append(entry)
            if status != 200 or body.startswith("__error__:"):
                continue
            if "html" not in (ctype or "").lower() and "<html" not in body[:200].lower():
                continue
            soup = BeautifulSoup(body, "lxml")
            cms = detect_cms(body, soup)

            sel, sels = looks_like_listing_classic(soup)
            method = "classic"
            sample_titles: list[str] = []
            items_count = 0
            # If classic returned a too-generic selector (li / tr / a alone),
            # try link-pattern and prefer if it gives a tighter scope.
            if sel in ("li", "tr", "a"):
                sel2, sels2, titles2 = looks_like_listing_by_link_pattern(soup, final)
                if sel2 and sel2 != sel:
                    sel, sels = sel2, sels2
                    sample_titles = titles2
                    method = "link-pattern"
            if sel:
                try:
                    rows = soup.select(sel)
                    items_count = len(rows)
                    for r in rows[:5]:
                        link = _row_link(r)
                        text = (
                            link.get_text(" ", strip=True)
                            if link
                            else r.get_text(" ", strip=True)
                        )
                        if len(text) >= 15 and text not in sample_titles:
                            sample_titles.append(text[:120])
                except Exception:
                    pass
            else:
                sel2, sels2, titles2 = looks_like_listing_by_link_pattern(soup, final)
                if sel2:
                    sel, sels = sel2, sels2
                    sample_titles = titles2
                    method = "link-pattern"
                    items_count = len(soup.select(sel)) if sel else 0

            if not sel:
                continue

            # Hardening: must have 5+ items
            if items_count < 5 and len(sample_titles) < 5:
                continue

            pagination = detect_pagination(soup) or {"type": "unknown"}

            candidate = {
                "press_release_url": final,
                "list_item": sels.get("list_item"),
                "title": sels.get("title"),
                "date": sels.get("date"),
                "detail_link": sels.get("detail_link", "a[href]"),
                "pagination": pagination,
                "parser_family": parser_family_from_cms(cms),
                "cms": cms,
                "sample_titles": sample_titles[:5],
                "items_found_on_page1": items_count,
                "selector_method": method,
                "discovered_via": source,
            }
            # Prefer URL with "press" in path; otherwise first hit wins.
            if best is None:
                best = candidate
            else:
                cur_score = sum(
                    1
                    for kw in ("press-release", "press_release", "press-center", "newsroom")
                    if kw in (best["press_release_url"] or "").lower()
                )
                new_score = sum(
                    1
                    for kw in ("press-release", "press_release", "press-center", "newsroom")
                    if kw in (candidate["press_release_url"] or "").lower()
                )
                if new_score > cur_score:
                    best = candidate
                # If items count is dramatically larger and url is reasonable, switch.
                elif candidate["items_found_on_page1"] > best["items_found_on_page1"] * 2:
                    best = candidate

            # Stop early if we found a strong press-release listing.
            if best and best["items_found_on_page1"] >= 5 and "press" in (
                best["press_release_url"] or ""
            ).lower():
                break

        elapsed = time.monotonic() - t0

        if best:
            print(
                f"  [OK] {mid:<28} {best['press_release_url']} "
                f"items={best['items_found_on_page1']:>3} sel={best['list_item']} "
                f"({elapsed:.1f}s)",
                flush=True,
            )
            return {
                "member_id": mid,
                "discovery": best,
                "tried_urls": [t["url"] for t in tried],
            }

        print(
            f"  [..] {mid:<28} no listing detected after {len(tried)} URLs "
            f"({elapsed:.1f}s)",
            flush=True,
        )
        return {
            "member_id": mid,
            "still_broken": True,
            "tried_urls": [t["url"] for t in tried],
            "reason": "no static-html listing matched any selector or link-pattern",
        }


async def run(limit: int | None = None, only_member: str | None = None):
    seed = json.loads(SEED_FILE.read_text())
    members = seed["members"]
    targets = [m for m in members if m.get("collection_method") is None]
    if only_member:
        targets = [m for m in targets if m["member_id"] == only_member]
    if limit:
        targets = targets[:limit]

    print(
        f"Unconfigured-house recon: {len(targets)} member(s), concurrency={MAX_CONCURRENT}"
    )

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    async with httpx.AsyncClient(
        headers=BROWSER_HEADERS,
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
        follow_redirects=True,
    ) as client:
        tasks = [probe_member(client, sem, m) for m in targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    found: dict[str, dict] = {}
    still_broken: list[dict] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            still_broken.append({
                "member_id": targets[i]["member_id"],
                "tried_urls": [],
                "reason": f"{type(r).__name__}: {r}",
            })
            continue
        if r.get("discovery"):
            found[r["member_id"]] = r["discovery"]
        else:
            still_broken.append({
                "member_id": r["member_id"],
                "tried_urls": r.get("tried_urls", []),
                "reason": r.get("reason", "unknown"),
            })

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "concurrency": MAX_CONCURRENT,
        "polite_delay_s": POLITE_DELAY,
        "url_guesses": URL_GUESSES,
        "selector_candidates": SELECTOR_CANDIDATES,
        "found": found,
        "still_broken": still_broken,
        "summary": {
            "total_targets": len(targets),
            "found_count": len(found),
            "still_broken_count": len(still_broken),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print()
    print(
        f"Found: {len(found)} / {len(targets)} | "
        f"Still broken: {len(still_broken)}"
    )
    print(f"Wrote {OUT_JSON}")


def main():
    parser = argparse.ArgumentParser(description="Recon for unconfigured House members")
    parser.add_argument("--limit", type=int, help="Probe only the first N targets")
    parser.add_argument("--member", help="Probe only one member by member_id")
    args = parser.parse_args()
    asyncio.run(run(limit=args.limit, only_member=args.member))


if __name__ == "__main__":
    main()
