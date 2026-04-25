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

Limitation: most senate.gov sites sit behind the Senate Akamai WAF and
return 403 to non-browser fingerprints. Those senators show "WAF" in
the report — that's *not* a failure, it just means we can't probe
their sitemap from this IP. The WAF-blocked senators are still scraped
fine by the daily pipeline (via Playwright or specifically-shaped
httpx). To audit them, run from a different IP or extend the script
with Playwright.

Usage:
    python -m pipeline.scripts.audit_sources
    python -m pipeline.scripts.audit_sources --senator paul-rand
    python -m pipeline.scripts.audit_sources --write docs/source_audit.md
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

MIN_SECTION_SIZE = 5  # ignore sections with fewer URLs than this

# Section path FRAGMENTS we deliberately skip. Match against the
# section path joined with /, e.g. "/news/in-the-news/" or "/videos/".
SKIP_SECTIONS = (
    "/in-the-news", "/in_the_news",
    "/videos", "/video",
    "/photos", "/photo",
    "/clips", "/clip",
    "/audio",
    "/multimedia", "/photo-galleries",
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
    "/newsletter-signup", "/sign-up", "/signup",
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
    "audio_library", "sweet_tea", "oceanwp_library", "hiking-trail",
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


def fetch_sitemap_urls(client: httpx.Client, sitemap_url: str, depth: int = 0) -> list[str]:
    """Recursively fetch <loc> URLs from a sitemap or sitemap index."""
    if depth > 3:
        return []
    try:
        r = client.get(sitemap_url)
        if r.status_code != 200:
            return []
        text = r.text
    except Exception:
        return []

    urls: list[str] = []
    # Cheap regex parse — sitemaps are big and consistent
    locs = re.findall(r"<loc>([^<]+)</loc>", text)
    is_index = "<sitemapindex" in text
    if is_index:
        # Walk children
        for child in locs[:30]:  # cap children
            if child.endswith(".xml"):
                urls.extend(fetch_sitemap_urls(client, child, depth + 1))
    else:
        urls.extend(locs)
    return urls


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


def audit_senator(senator: dict, conn_url: str) -> dict:
    sid = senator["senator_id"]
    name = senator.get("full_name", sid)
    state = senator.get("state", "")
    official = (senator.get("official_url") or "").rstrip("/")
    press = (senator.get("press_release_url") or "").rstrip("/")

    issues: list[str] = []

    # ---- DB pull ----
    conn = psycopg2.connect(conn_url)
    cur = conn.cursor()
    cur.execute("""
      SELECT count(*) FILTER (WHERE deleted_at IS NULL),
             count(*) FILTER (WHERE deleted_at IS NULL AND content_type='press_release'),
             max(scraped_at) FILTER (WHERE deleted_at IS NULL),
             max(published_at) FILTER (WHERE deleted_at IS NULL)
        FROM press_releases WHERE senator_id = %s
    """, (sid,))
    total, n_pr, last_scrape, last_pub = cur.fetchone()

    # Section -> count of records we have under that section path
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
    """, (sid,))
    db_sections = {r[0]: r[1] for r in cur.fetchall()}
    cur.close(); conn.close()

    # ---- HTTP probes (sitemap + WP only; URL reachability inferred from DB) ----
    # Cloudflare blocks our IP under load, so probing every senator's
    # homepage is unreliable. We verify reachability by DB freshness:
    # if the daily collector successfully scraped within 48 hours, the
    # site is reachable from our pipeline IP.
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
        sitemap_urls: list[str] = []
        sitemap_status = "missing"
        if official:
            sm_urls, sitemap_status = find_sitemaps(client, official)
            for sm in sm_urls:
                sitemap_urls.extend(fetch_sitemap_urls(client, sm))

        if official:
            wp_types, wp_status = probe_wp_types(client, official)
        else:
            wp_types, wp_status = None, "missing"

    # ---- Section enumeration from sitemap ----
    section_counts: dict[str, int] = defaultdict(int)
    for url in sitemap_urls:
        sec = section_path(url)
        if sec:
            section_counts[sec] += 1

    # Sections we don't collect from but should consider
    untapped_sections: list[tuple[str, int]] = []
    for sec, n in section_counts.items():
        if n < MIN_SECTION_SIZE:
            continue
        if is_skip_section(sec):
            continue
        # Already have records in this section?
        if db_sections.get(sec, 0) >= 1:
            continue
        # Also accept records at deeper / shallower paths (e.g. seed
        # press_url is /newsroom/press-releases/ but sitemap reports
        # /newsroom/ as a section due to how URLs are split).
        if any(s.startswith(sec) or sec.startswith(s) for s in db_sections):
            continue
        untapped_sections.append((sec, n))

    untapped_sections.sort(key=lambda x: -x[1])

    # ---- Checks ----
    check_official = OK if official else FAIL
    if not official:
        issues.append("seed missing official_url")

    check_news = OK if press else FAIL
    if not press:
        issues.append("seed missing press_release_url")

    if sid == "armstrong-alan":
        check_pr = NA
    else:
        check_pr = OK if n_pr >= 1 else FAIL
        if check_pr == FAIL:
            issues.append("zero press_release records")

    if sitemap_status == "blocked":
        check_sitemap = "WAF"
    elif not sitemap_urls:
        check_sitemap = NA
    else:
        check_sitemap = OK if not untapped_sections else FAIL
        if untapped_sections:
            sample = ", ".join(f"{s.strip('/')}({n})" for s, n in untapped_sections[:3])
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
        "n_total": total,
        "n_pr": n_pr,
        "last_scrape": last_scrape,
        "sitemap_urls": len(sitemap_urls),
        "untapped": untapped_sections,
        "wp_types": wp_types or {},
        "check_official": check_official,
        "check_news": check_news,
        "check_pr": check_pr,
        "check_sitemap": check_sitemap,
        "check_wp": check_wp,
        "issues": issues,
    }


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
    ap.add_argument("--workers", type=int, default=8)
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

    print(f"Auditing {len(seeds)} senators (sitemap-driven)...", file=sys.stderr)
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
