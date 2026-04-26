"""Per-senator source-coverage audit, sitemap-driven.

For every member, verify:

  1. official_url resolves
  2. press_release_url resolves
  3. We have >=1 press_release record (Armstrong allowlisted)
  4. EVERY section that the senator's site publishes (per sitemap.xml)
     is either:
       - a section we already collect from (>=1 DB record), OR
       - explicitly skipped (in_the_news, videos, photos, events,
         about, contact, services, issues, legislation, ...), OR
       - too thin to matter (<MIN_SECTION_SIZE URLs)
  5. As a backstop, WP `/wp-json/wp/v2/types` is enumerated and any
     custom post type with content is either collected or skip-listed.

Sitemap discovery order:
    /robots.txt -> Sitemap: lines
    /sitemap_index.xml -> walks <sitemap><loc>...</loc></sitemap>
    /wp-sitemap.xml (WP)
    /sitemap.xml

Two-pass design:
    Pass 1 — httpx, parallel, fast. Most senators clear here.
    Pass 2 — Playwright, sequential with back-off, for senators that
             return 403 to httpx (Senate Akamai WAF). Real Chrome
             fingerprint + per-senator cooldown bypasses the WAF.

If both passes return 403 for a senator, the report shows "WAF" — a
known unprobeable state, not a coverage gap. (Akamai also rate-limits
by source IP. Run from a different IP or wait if many "WAF" persist.)

Usage:
    python -m pipeline.scripts.audit_sources
    python -m pipeline.scripts.audit_sources --senator paul-rand
    python -m pipeline.scripts.audit_sources --write docs/source_audit.md
    python -m pipeline.scripts.audit_sources --no-playwright   # skip pass 2
    python -m pipeline.scripts.audit_sources --pw-delay 15     # gentler pass 2
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import httpx
import psycopg2
from bs4 import BeautifulSoup

from pipeline.backfill_wp_json import load_env

MIN_SECTION_SIZE = 10  # ignore sections with fewer URLs than this

# Section path FRAGMENTS we deliberately skip. Match against the
# section path joined with /, e.g. "/news/in-the-news/" or "/videos/".
SKIP_SECTIONS = (
    "/in-the-news", "/in_the_news",
    "/videos", "/video",
    "/photos", "/photo",
    "/clips", "/clip",
    "/audio",
    "/multimedia", "/photo-galleries", "-photo-galleries",
    "/news-coverage",  # press clippings, not original
    "/events", "/event", "/upcoming-events",
    "/about", "/biography", "/bio",
    "/contact",
    "/services", "/help", "/casework", "/get-help",
    "/issues",
    "/legislation",
    "/committee", "/committees",
    "/constituent", "/student", "/students", "/delawareans",
    "/internship", "/jobs", "/employment",
    "/visiting", "/visit", "/tours", "/flag",
    "/newsletter-signup", "/sign-up", "/signup", "/join-newsletter",
    "/privacy", "/accessibility", "/terms",
    "/connect", "/serving-you",
    "/wp-content", "/wp-admin", "/wp-includes", "/wp-json",
    "/feed", "/rss",
    "/category/", "/tag/", "/author/",
    "/page/",
    "/search",
    "/download/",  # PDFs, images
    "/coronavirus/",  # dated landing pages
    "/priorities",
    "/spending-requests",
    "/grants",
    "/es/", "/es-mx/",  # Spanish mirrors -- duplicates of EN content
    "/ultimas-noticias", "/comunicados", "/comunicados-de-prensa",
    "/jet-popup", "/popup",
    "/meet-", "/working-for-",
    "/2021/", "/2022/", "/2023/", "/2024/",  # pre-window year archives
)

# Year-archive pattern: /YYYY/MM/ or /YYYY/ at the leaf -- treat as skip
YEAR_ARCHIVE = re.compile(r"^/(19|20)\d{2}(/\d{1,2})?/?$")

# WP custom post types we recognize.
WP_KNOWN_COLLECTED = {
    "press_releases", "press_release", "posts", "post", "news",
    "op_eds", "op_ed",
    "newsletter", "newsletters", "bernie-buzz",
    "blogs", "blog",
    "speeches", "remarks",
    "statements", "statement",
    "letters", "letter",
    "floor_statements", "floor_statement",
    "sweet_tea",
}
WP_KNOWN_SKIP = {
    "page", "attachment", "wp_block", "wp_template", "wp_template_part",
    "wp_navigation", "nav_menu_item", "wp_global_styles", "custom_css",
    "customize_changeset", "oembed_cache", "user_request",
    "wp_font_face", "wp_font_family",
    "in_the_news", "in-the-news",
    "videos", "video", "photos", "photo", "image",
    "events", "event",
    "tribe_events", "tribe_venue", "tribe_organizer", "tribe_ea_record",
    "tribe-ea-record", "tec_calendar_embed", "vt-events", "csc_events",
    "weekly_column",
    "elementor_library", "e-landing-page", "elementor_snippet",
    "e-floating-buttons",
    "jet-popup", "jet-menu", "jet-engine",
    "udb_admin_page", "udb_block_template",
    "csc-pages", "csc_press_release", "csc_featured",
    "spending_requests", "priorities", "project", "map-post",
    "success-story", "locations", "location", "r-location",
    "alert", "alert-banner", "site-alerts",
    "audio_library", "oceanwp_library", "hiking-trail",
    "schedule", "news_sources", "issues", "legislation",
    "shortcuts", "rec-products", "amn_smtp", "wpcf7_contact_form",
}

OK = "OK"
FAIL = "FAIL"
NA = "n/a"


def fetch(client: httpx.Client, url: str) -> tuple[int, str]:
    try:
        r = client.get(url)
        return r.status_code, r.text if r.status_code == 200 else ""
    except Exception:
        return 0, ""


def find_sitemaps(client: httpx.Client, base: str) -> tuple[list[str], str]:
    """Discover sitemap URLs for a site.

    Returns (sitemap_urls, status). Status is one of:
        "ok"      — found at least one sitemap
        "blocked" — every probe returned 403 (Senate Akamai WAF)
        "missing" — probes returned 200/404 but no sitemap was found
    """
    found: list[str] = []
    saw_403 = False
    saw_other = False

    try:
        r = client.get(f"{base}/robots.txt")
        if r.status_code == 200:
            for line in r.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sm = line.split(":", 1)[1].strip()
                    if sm and sm not in found:
                        found.append(sm)
        elif r.status_code == 403:
            saw_403 = True
        else:
            saw_other = True
    except Exception:
        pass

    for url in (
        f"{base}/sitemap_index.xml",
        f"{base}/wp-sitemap.xml",
        f"{base}/sitemap.xml",
    ):
        if url in found:
            continue
        try:
            r = client.get(url)
            if r.status_code == 200 and ("<urlset" in r.text or "<sitemapindex" in r.text):
                found.append(url)
            elif r.status_code == 403:
                saw_403 = True
            else:
                saw_other = True
        except Exception:
            continue

    if found:
        return found, "ok"
    if saw_403 and not saw_other:
        return [], "blocked"
    return [], "missing"


URL_LASTMOD_RE = re.compile(
    r"<url>\s*<loc>([^<]+)</loc>(?:[^<]*<lastmod>([^<]+)</lastmod>)?",
    re.DOTALL,
)


def fetch_sitemap_urls(client: httpx.Client, sitemap_url: str, depth: int = 0) -> list[str]:
    """Recursively fetch <loc> URLs from a sitemap or sitemap index."""
    return [u for (u, _) in fetch_sitemap_with_lastmod(client, sitemap_url, depth)]


def fetch_sitemap_with_lastmod(
    client: httpx.Client, sitemap_url: str, depth: int = 0
) -> list[tuple[str, str | None]]:
    """Recursively fetch (url, lastmod) tuples from a sitemap or sitemap index."""
    if depth > 3:
        return []
    try:
        r = client.get(sitemap_url)
        if r.status_code != 200:
            return []
        text = r.text
    except Exception:
        return []

    is_index = "<sitemapindex" in text
    if is_index:
        out: list[tuple[str, str | None]] = []
        children = re.findall(r"<loc>([^<]+)</loc>", text)
        for child in children[:30]:
            if child.endswith(".xml"):
                out.extend(fetch_sitemap_with_lastmod(client, child, depth + 1))
        return out
    return [(m.group(1), m.group(2)) for m in URL_LASTMOD_RE.finditer(text)]


def section_path(url: str) -> str | None:
    """Extract the section path (first 1-2 segments under host)."""
    try:
        p = urlparse(url)
        if not p.path or p.path == "/":
            return None
        parts = [x for x in p.path.split("/") if x]
        if len(parts) < 2:
            return f"/{parts[0]}/" if parts else None
        # Keep two segments for nested newsrooms (e.g. /news/press-releases/)
        return f"/{parts[0]}/{parts[1]}/"
    except Exception:
        return None


def is_skip_section(section: str) -> bool:
    s = section.lower()
    if YEAR_ARCHIVE.match(s.rstrip("/") + "/"):
        return True
    for marker in SKIP_SECTIONS:
        if marker in s:
            return True
    return False


def probe_wp_types(client: httpx.Client, base: str) -> tuple[dict[str, int] | None, str]:
    """Returns (types_with_counts, status). Status one of: ok, blocked, missing."""
    try:
        r = client.get(f"{base}/wp-json/wp/v2/types")
        if r.status_code == 403:
            return None, "blocked"
        if r.status_code != 200:
            return None, "missing"
        types = r.json()
        if not isinstance(types, dict):
            return None, "missing"
    except Exception:
        return None, "missing"

    out: dict[str, int] = {}
    for slug, info in types.items():
        if not isinstance(info, dict) or not info.get("rest_base"):
            continue
        if slug in WP_KNOWN_SKIP:
            continue
        if slug in {"posts", "post", "page", "attachment"}:
            continue
        try:
            rb = info.get("rest_base", slug)
            r2 = client.get(
                f"{base}/wp-json/wp/v2/{rb}",
                params={"per_page": 1, "after": "2025-01-01T00:00:00"},
            )
            if r2.status_code != 200:
                continue
            total = int(r2.headers.get("x-wp-total", "0") or 0)
            if total >= MIN_SECTION_SIZE:
                out[slug] = total
        except Exception:
            continue
    return out, "ok"


BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def pull_db_state(conn_url: str, senator_id: str) -> dict:
    conn = psycopg2.connect(conn_url)
    cur = conn.cursor()
    cur.execute("""
      SELECT count(*) FILTER (WHERE deleted_at IS NULL),
             count(*) FILTER (WHERE deleted_at IS NULL AND content_type='press_release'),
             max(scraped_at) FILTER (WHERE deleted_at IS NULL),
             max(published_at) FILTER (WHERE deleted_at IS NULL)
        FROM press_releases WHERE senator_id = %s
    """, (senator_id,))
    total, n_pr, last_scrape, last_pub = cur.fetchone()

    cur.execute("""
      WITH paths AS (
        SELECT regexp_replace(source_url,
            '^https?://[^/]+(/[^/]+(?:/[^/]+)?/).*$', '\\1') AS section
        FROM press_releases
        WHERE senator_id = %s AND deleted_at IS NULL
      )
      SELECT section, count(*) FROM paths
      WHERE section LIKE '/%%'
      GROUP BY section
    """, (senator_id,))
    db_sections = {r[0]: r[1] for r in cur.fetchall()}
    cur.close(); conn.close()
    return {
        "n_total": total,
        "n_pr": n_pr,
        "last_scrape": last_scrape,
        "db_sections": db_sections,
    }


def httpx_probe(official: str) -> dict:
    """Probe sitemap + WP types via httpx. Returns {sitemap_urls, sitemap_status, wp_types, wp_status}."""
    if not official:
        return {"sitemap_urls": [], "sitemap_lastmods": [],
                "sitemap_status": "missing", "wp_types": None, "wp_status": "missing"}
    with httpx.Client(timeout=20, follow_redirects=True, headers=BROWSER_HEADERS) as client:
        sm_urls, sitemap_status = find_sitemaps(client, official)
        pairs: list[tuple[str, str | None]] = []
        for sm in sm_urls:
            pairs.extend(fetch_sitemap_with_lastmod(client, sm))
        wp_types, wp_status = probe_wp_types(client, official)
    return {
        "sitemap_urls": [u for (u, _) in pairs],
        "sitemap_lastmods": pairs,
        "sitemap_status": sitemap_status,
        "wp_types": wp_types,
        "wp_status": wp_status,
    }


def classify(senator: dict, db_state: dict, probe: dict) -> dict:
    """Combine seed + DB + probe into final audit row."""
    sid = senator["senator_id"]
    name = senator.get("full_name", sid)
    state = senator.get("state", "")
    official = (senator.get("official_url") or "").rstrip("/")
    press = (senator.get("press_release_url") or "").rstrip("/")
    issues: list[str] = []

    sitemap_urls = probe["sitemap_urls"]
    sitemap_status = probe["sitemap_status"]
    wp_types = probe["wp_types"]
    wp_status = probe["wp_status"]
    db_sections = db_state["db_sections"]

    section_counts: dict[str, int] = defaultdict(int)
    section_in_window: dict[str, int] = defaultdict(int)
    section_has_lastmod: dict[str, bool] = defaultdict(bool)
    pairs = probe.get("sitemap_lastmods") or [(u, None) for u in sitemap_urls]
    for url, lm in pairs:
        sec = section_path(url)
        if not sec:
            continue
        section_counts[sec] += 1
        if lm:
            section_has_lastmod[sec] = True
            if lm >= "2025-01-01":
                section_in_window[sec] += 1
        elif "/2025" in url or "/2026" in url:
            section_in_window[sec] += 1

    untapped_sections: list[tuple[str, int]] = []
    archival_sections: list[tuple[str, int]] = []
    for sec, n in section_counts.items():
        if n < MIN_SECTION_SIZE:
            continue
        if is_skip_section(sec):
            continue
        if db_sections.get(sec, 0) >= 1:
            continue
        if any(s.startswith(sec) or sec.startswith(s) for s in db_sections):
            continue
        if section_has_lastmod[sec] and section_in_window[sec] == 0:
            archival_sections.append((sec, n))
            continue
        untapped_sections.append((sec, n))
    untapped_sections.sort(key=lambda x: -x[1])
    archival_sections.sort(key=lambda x: -x[1])

    # Liveness HEAD-probe: distinguish stale sitemap entries (404) from
    # genuinely-untapped live sections. Section URL = official + section.
    untapped_live: list[tuple[str, int]] = []
    untapped_dead: list[tuple[str, int, int]] = []  # (sec, n, status)
    if official and untapped_sections:
        with httpx.Client(timeout=10, follow_redirects=True, headers=BROWSER_HEADERS) as c:
            for sec, n in untapped_sections:
                url = official + sec
                try:
                    r = c.head(url)
                    if r.status_code == 405:  # method not allowed; retry GET
                        r = c.get(url)
                    status = r.status_code
                except Exception:
                    status = 0
                if status == 404 or status == 410:
                    untapped_dead.append((sec, n, status))
                else:
                    untapped_live.append((sec, n))

    check_official = OK if official else FAIL
    if not official:
        issues.append("seed missing official_url")
    check_news = OK if press else FAIL
    if not press:
        issues.append("seed missing press_release_url")

    if sid == "armstrong-alan":
        check_pr = NA
    else:
        check_pr = OK if db_state["n_pr"] >= 1 else FAIL
        if check_pr == FAIL:
            issues.append("zero press_release records")

    if sitemap_status == "blocked":
        check_sitemap = "WAF"
    elif not sitemap_urls:
        check_sitemap = NA
    else:
        check_sitemap = OK if not untapped_live else FAIL
        if untapped_live:
            sample = ", ".join(f"{s.strip('/')}({n})" for s, n in untapped_live[:3])
            issues.append(f"sitemap-untapped: {sample}")

    if wp_status == "blocked":
        check_wp = "WAF"
    elif wp_types is None:
        check_wp = NA
    else:
        unknown_pt = []
        for slug, n in wp_types.items():
            if slug in WP_KNOWN_COLLECTED:
                continue
            unknown_pt.append(f"{slug}({n})")
        check_wp = OK if not unknown_pt else FAIL
        if unknown_pt:
            issues.append(f"unclassified WP post types: {', '.join(unknown_pt[:5])}")

    return {
        "senator_id": sid,
        "name": name,
        "state": state,
        "n_total": db_state["n_total"],
        "n_pr": db_state["n_pr"],
        "last_scrape": db_state["last_scrape"],
        "sitemap_urls": len(sitemap_urls),
        "untapped": untapped_live,
        "untapped_dead": untapped_dead,
        "archival": archival_sections,
        "wp_types": wp_types or {},
        "check_official": check_official,
        "check_news": check_news,
        "check_pr": check_pr,
        "check_sitemap": check_sitemap,
        "check_wp": check_wp,
        "issues": issues,
        "probe_method": probe.get("method", "httpx"),
    }


def audit_senator(senator: dict, conn_url: str) -> dict:
    """httpx-only audit (the parallel-fast path)."""
    sid = senator["senator_id"]
    official = (senator.get("official_url") or "").rstrip("/")
    db_state = pull_db_state(conn_url, sid)
    probe = httpx_probe(official)
    probe["method"] = "httpx"
    return classify(senator, db_state, probe)


# ----- Playwright fallback for WAF-blocked senators -----

def _pw_fetch_text(ctx, url: str) -> tuple[int, str]:
    """Fetch a URL via the Playwright context's request stack."""
    try:
        r = ctx.request.get(url, timeout=20000)
        try:
            txt = r.text()
        except Exception:
            txt = ""
        return r.status, txt
    except Exception:
        return 0, ""


def _pw_find_sitemaps(ctx, base: str) -> tuple[list[str], str]:
    found: list[str] = []
    saw_403 = False
    saw_other = False

    code, txt = _pw_fetch_text(ctx, f"{base}/robots.txt")
    if code == 200:
        for line in txt.splitlines():
            if line.lower().startswith("sitemap:"):
                sm = line.split(":", 1)[1].strip()
                if sm and sm not in found:
                    found.append(sm)
    elif code == 403:
        saw_403 = True
    elif code:
        saw_other = True

    for url in (
        f"{base}/sitemap_index.xml",
        f"{base}/wp-sitemap.xml",
        f"{base}/sitemap.xml",
    ):
        if url in found:
            continue
        code, txt = _pw_fetch_text(ctx, url)
        if code == 200 and ("<urlset" in txt or "<sitemapindex" in txt):
            found.append(url)
        elif code == 403:
            saw_403 = True
        elif code:
            saw_other = True

    if found:
        return found, "ok"
    if saw_403 and not saw_other:
        return [], "blocked"
    return [], "missing"


def _pw_walk_sitemap(ctx, sitemap_url: str, depth: int = 0) -> list[str]:
    if depth > 3:
        return []
    code, txt = _pw_fetch_text(ctx, sitemap_url)
    if code != 200:
        return []
    urls: list[str] = []
    locs = re.findall(r"<loc>([^<]+)</loc>", txt)
    if "<sitemapindex" in txt:
        for child in locs[:30]:
            if child.endswith(".xml"):
                urls.extend(_pw_walk_sitemap(ctx, child, depth + 1))
    else:
        urls.extend(locs)
    return urls


def _pw_probe_wp_types(ctx, base: str) -> tuple[dict[str, int] | None, str]:
    code, txt = _pw_fetch_text(ctx, f"{base}/wp-json/wp/v2/types")
    if code == 403:
        return None, "blocked"
    if code != 200 or not txt:
        return None, "missing"
    try:
        types = json.loads(txt)
        if not isinstance(types, dict):
            return None, "missing"
    except Exception:
        return None, "missing"

    out: dict[str, int] = {}
    for slug, info in types.items():
        if not isinstance(info, dict) or not info.get("rest_base"):
            continue
        if slug in WP_KNOWN_SKIP:
            continue
        if slug in {"posts", "post", "page", "attachment"}:
            continue
        rb = info.get("rest_base", slug)
        url = f"{base}/wp-json/wp/v2/{rb}?per_page=1&after=2025-01-01T00:00:00"
        try:
            r2 = ctx.request.get(url, timeout=20000)
            if r2.status != 200:
                continue
            total = int(r2.headers.get("x-wp-total", "0") or 0)
            if total >= MIN_SECTION_SIZE:
                out[slug] = total
        except Exception:
            continue
    return out, "ok"


# ----- Wayback Machine fallback -----
# When even Playwright hits Akamai (IP-level rate limit), fall back
# to archive.org. The Wayback Machine has cached copies of senate.gov
# sitemaps and is not WAF'd.

WAYBACK_TS = "2026"  # year to ask for; wayback redirects to closest


def _wayback_url(url: str) -> str:
    return f"https://web.archive.org/web/{WAYBACK_TS}id_/{url}"


def _wb_fetch(client: httpx.Client, url: str) -> tuple[int, str]:
    try:
        r = client.get(_wayback_url(url))
        return r.status_code, r.text if r.status_code == 200 else ""
    except Exception:
        return 0, ""


def wayback_probe(official: str) -> dict:
    """Fetch sitemap via Wayback. WP types we don't try (Wayback rarely caches API)."""
    if not official:
        return {"sitemap_urls": [], "sitemap_status": "missing",
                "wp_types": None, "wp_status": "missing", "method": "wayback"}
    found_sm: list[str] = []
    sitemap_urls: list[str] = []
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        # Try robots.txt first
        code, txt = _wb_fetch(client, f"{official}/robots.txt")
        if code == 200:
            for line in txt.splitlines():
                if line.lower().startswith("sitemap:"):
                    sm = line.split(":", 1)[1].strip()
                    if sm and sm not in found_sm:
                        found_sm.append(sm)
        for u in (
            f"{official}/sitemap_index.xml",
            f"{official}/wp-sitemap.xml",
            f"{official}/sitemap.xml",
        ):
            if u in found_sm:
                continue
            code, txt = _wb_fetch(client, u)
            if code == 200 and ("<urlset" in txt or "<sitemapindex" in txt):
                found_sm.append(u)

        def walk(sm_url: str, depth: int = 0) -> None:
            if depth > 3:
                return
            code, txt = _wb_fetch(client, sm_url)
            if code != 200:
                return
            locs = re.findall(r"<loc>([^<]+)</loc>", txt)
            if "<sitemapindex" in txt:
                for child in locs[:30]:
                    if child.endswith(".xml"):
                        walk(child, depth + 1)
            else:
                sitemap_urls.extend(locs)
        for sm in found_sm:
            walk(sm)

    if sitemap_urls:
        return {"sitemap_urls": sitemap_urls, "sitemap_status": "ok",
                "wp_types": None, "wp_status": "missing", "method": "wayback"}
    return {"sitemap_urls": [], "sitemap_status": "missing",
            "wp_types": None, "wp_status": "missing", "method": "wayback"}


def playwright_probe_batch(senators: list[dict], per_senator_delay: float = 8.0) -> dict[str, dict]:
    """Open one browser, iterate through senators with back-off, probe each.

    For each senator: open a fresh context, visit homepage (sets WAF
    cookies + lets challenge JS run), then fetch sitemap + WP types via
    the same browser context. Real Chrome fingerprint + per-senator
    cooldown bypasses Akamai. Slow but reliable.
    """
    from playwright.sync_api import sync_playwright
    import time as _time

    out: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for i, s in enumerate(senators):
                sid = s["senator_id"]
                official = (s.get("official_url") or "").rstrip("/")
                if not official:
                    out[sid] = {
                        "sitemap_urls": [], "sitemap_status": "missing",
                        "wp_types": None, "wp_status": "missing",
                        "method": "playwright",
                    }
                    continue
                ctx = browser.new_context(
                    user_agent=BROWSER_HEADERS["User-Agent"],
                    viewport={"width": 1280, "height": 800},
                    locale="en-US",
                )
                page = ctx.new_page()
                try:
                    page.goto(official, wait_until="networkidle", timeout=30000)
                except Exception:
                    try:
                        page.goto(official, wait_until="domcontentloaded", timeout=20000)
                    except Exception as e:
                        print(f"\n[{sid}] homepage load failed: {e}", file=sys.stderr)
                _time.sleep(1.5)  # let WAF challenge JS settle

                sm_urls, sitemap_status = _pw_find_sitemaps(ctx, official)
                sitemap_urls: list[str] = []
                for sm in sm_urls:
                    sitemap_urls.extend(_pw_walk_sitemap(ctx, sm))
                wp_types, wp_status = _pw_probe_wp_types(ctx, official)

                out[sid] = {
                    "sitemap_urls": sitemap_urls,
                    "sitemap_status": sitemap_status,
                    "wp_types": wp_types,
                    "wp_status": wp_status,
                    "method": "playwright",
                }
                ctx.close()
                marker = "+" if sitemap_status == "ok" else ("." if sitemap_status == "missing" else "x")
                print(marker, end="", flush=True, file=sys.stderr)

                if i + 1 < len(senators):
                    _time.sleep(per_senator_delay)
        finally:
            browser.close()
    return out


def render(rows: list[dict]) -> str:
    failed = [r for r in rows if FAIL in (
        r["check_official"], r["check_news"],
        r["check_pr"], r["check_sitemap"], r["check_wp"]
    )]

    out = ["# Source-Coverage Audit — sitemap-driven\n"]
    out.append(f"Audited: {len(rows)} senators. Failing at least one check: {len(failed)}.\n")
    out.append("Checks:\n")
    out.append("- **seed** = both official_url and press_release_url present in seed config")
    out.append("- **PR** = >=1 press_release record (Armstrong allowlisted)")
    out.append("- **sm** = every sitemap section is either collected or in SKIP list")
    out.append("- **wp** = no unclassified WP custom post types\n")

    if failed:
        out.append("## Senators needing attention\n")
        out.append("| State | Senator | seed | PR | sm | wp | Issues |")
        out.append("|---|---|---|---|---|---|---|")
        for r in failed:
            seed_check = OK if r["check_official"] == OK and r["check_news"] == OK else FAIL
            out.append(f"| {r['state']} | {r['name']} | {seed_check} | {r['check_pr']} | {r['check_sitemap']} | {r['check_wp']} | {'<br>'.join(r['issues'])} |")
        out.append("")

    # Untapped silos roll-up — every (senator, section, count) sorted by volume.
    silos: list[tuple[int, str, str, str]] = []
    for r in rows:
        for sec, n in r.get("untapped", []):
            silos.append((n, r["state"], r["name"], sec))
    if silos:
        silos.sort(reverse=True)
        out.append("## Untapped silos (every (senator, section) sorted by volume)\n")
        out.append("| Count | State | Senator | Section |")
        out.append("|---:|---|---|---|")
        for n, st, name, sec in silos:
            out.append(f"| {n:,} | {st} | {name} | `{sec}` |")
        out.append("")

    # Archival sections — sitemap entries with lastmod data but zero in-window URLs.
    archival: list[tuple[int, str, str, str]] = []
    for r in rows:
        for sec, n in r.get("archival", []) or []:
            archival.append((n, r["state"], r["name"], sec))
    if archival:
        archival.sort(reverse=True)
        out.append("## Archival sections (sitemap lastmod < 2025-01-01)\n")
        out.append("Live sections that the sitemap classifies as pre-window only. ")
        out.append("Treat as informational — no in-window content to collect.\n")
        out.append("| Count | State | Senator | Section |")
        out.append("|---:|---|---|---|")
        for n, st, name, sec in archival:
            out.append(f"| {n:,} | {st} | {name} | `{sec}` |")
        out.append("")

    # Stale sitemap entries — sitemap URLs that 404 on the live site.
    stale: list[tuple[int, str, str, str, int]] = []
    for r in rows:
        for sec, n, status in r.get("untapped_dead", []) or []:
            stale.append((n, r["state"], r["name"], sec, status))
    if stale:
        stale.sort(reverse=True)
        out.append("## Stale sitemap entries (404/410 on live site)\n")
        out.append("These sections appear in the sitemap but the URL is dead. ")
        out.append("Treat as informational — not coverage gaps.\n")
        out.append("| Count | State | Senator | Section | Status |")
        out.append("|---:|---|---|---|---:|")
        for n, st, name, sec, status in stale:
            out.append(f"| {n:,} | {st} | {name} | `{sec}` | {status} |")
        out.append("")

    # Counts of each status, so it's easy to see overall health
    n_waf = sum(1 for r in rows if r["check_sitemap"] == "WAF" or r["check_wp"] == "WAF")
    n_probed = sum(1 for r in rows if r["sitemap_urls"] > 0)
    out.append(f"_Probed via sitemap: {n_probed}/{len(rows)}. Akamai-blocked (both passes): {n_waf}._\n")

    out.append("## Full table (alphabetical by state)\n")
    out.append("| State | Senator | seed | PR | sm | wp | sitemap URLs | Total recs |")
    out.append("|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: (x["state"], x["name"])):
        seed_check = OK if r["check_official"] == OK and r["check_news"] == OK else FAIL
        out.append(f"| {r['state']} | {r['name']} | {seed_check} | {r['check_pr']} | {r['check_sitemap']} | {r['check_wp']} | {r['sitemap_urls']:,} | {r['n_total']:,} |")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--senator", help="Audit only one senator_id")
    ap.add_argument("--write", help="Write the report to this path")
    ap.add_argument("--workers", type=int, default=2,
                    help="httpx parallelism (low default to avoid tripping Akamai)")
    ap.add_argument("--no-playwright", action="store_true",
                    help="Skip the Playwright second pass for WAF-blocked senators")
    ap.add_argument("--pw-delay", type=float, default=8.0,
                    help="Seconds between Playwright probes (back-off vs Akamai)")
    args = ap.parse_args()

    load_env()
    seeds_path = Path(__file__).resolve().parents[1] / "seeds" / "senate.json"
    seeds = json.load(open(seeds_path))["members"]
    if args.senator:
        seeds = [s for s in seeds if s["senator_id"] == args.senator]
        if not seeds:
            print(f"No senator matched: {args.senator}", file=sys.stderr)
            sys.exit(1)

    db_url = os.environ["DATABASE_URL"]
    seed_by_id = {s["senator_id"]: s for s in seeds}

    print(f"Pass 1 (httpx): {len(seeds)} senators...", file=sys.stderr)
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(audit_senator, s, db_url): s["senator_id"] for s in seeds}
        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                rows.append(fut.result())
                print(".", end="", flush=True, file=sys.stderr)
            except Exception as e:
                print(f"\n[{sid}] error: {e}", file=sys.stderr)
    print("", file=sys.stderr)

    # Pass 2: Wayback Machine for senators that httpx couldn't reach.
    # Wayback isn't Akamai-blocked, so it always works. We use it before
    # Playwright because it's cheaper and IP-rate-limit-free.
    blocked = [r for r in rows if r["check_sitemap"] == "WAF"]
    if blocked:
        print(f"Pass 2 (wayback): {len(blocked)} senators...", file=sys.stderr)
        row_by_id = {r["senator_id"]: r for r in rows}
        with ThreadPoolExecutor(max_workers=min(args.workers, 4)) as ex:
            futs = {ex.submit(wayback_probe, (seed_by_id[r["senator_id"]].get("official_url") or "").rstrip("/")): r["senator_id"] for r in blocked}
            for fut in as_completed(futs):
                sid = futs[fut]
                try:
                    probe = fut.result()
                except Exception as e:
                    print(f"\n[{sid}] wayback err: {e}", file=sys.stderr)
                    continue
                if probe["sitemap_status"] == "ok":
                    seed = seed_by_id[sid]
                    db_state = pull_db_state(db_url, sid)
                    row_by_id[sid] = classify(seed, db_state, probe)
                    print("w", end="", flush=True, file=sys.stderr)
                else:
                    print(".", end="", flush=True, file=sys.stderr)
        print("", file=sys.stderr)
        rows = list(row_by_id.values())

    # Pass 3: Playwright for senators still WAF (sitemap might just be
    # missing-from-Wayback, or we want WP types data). Optional.
    if not args.no_playwright:
        still_blocked = [r for r in rows if r["check_sitemap"] == "WAF" or r["check_wp"] == "WAF"]
        if still_blocked:
            print(f"Pass 3 (playwright): {len(still_blocked)} senators...",
                  file=sys.stderr)
            blocked_seeds = [seed_by_id[r["senator_id"]] for r in still_blocked]
            pw_results = playwright_probe_batch(blocked_seeds, per_senator_delay=args.pw_delay)
            print("", file=sys.stderr)
            row_by_id = {r["senator_id"]: r for r in rows}
            for sid, probe in pw_results.items():
                if probe["sitemap_status"] != "ok" and probe["wp_status"] != "ok":
                    continue
                seed = seed_by_id[sid]
                db_state = pull_db_state(db_url, sid)
                row_by_id[sid] = classify(seed, db_state, probe)
            rows = list(row_by_id.values())

    report = render(rows)
    print(report)
    if args.write:
        Path(args.write).write_text(report)
        print(f"\nWrote {args.write}", file=sys.stderr)

    failures = sum(1 for r in rows if FAIL in (
        r["check_official"], r["check_news"],
        r["check_pr"], r["check_sitemap"], r["check_wp"]
    ))
    sys.exit(0 if failures == 0 else 2)


if __name__ == "__main__":
    main()
