"""Bulk-collect House press releases via WordPress JSON API.

10 House members run on WordPress and expose `/wp-json/wp/v2/posts` with
deep coverage (70-1,442 posts each in their press-release category).
Their HTML listing — what the daily collector walks — is shallow
(~10 items), so HTML backfill alone leaves a big gap. This script
mirrors `backfill_op_eds.py` for the Senate WP custom post types,
retargeted to House `posts` filtered by category.

Members and upstream counts (per Bucket C agent recon, 2026-05-02):
    jeffries-hakeem      1,048 posts (NY-8, House Minority Leader)
    pressley-ayanna      1,442 posts (MA-7)
    brownley-julia         950 posts (CA-26)
    schweikert-david       646 posts (AZ-1)
    buchanan-vern          469 posts (FL-16)
    kiggans-jennifer       320 posts (VA-2)
    goodlander-maggie      295 posts (NH-2)
    crane-elijah           135 posts (AZ-2)
    baumgartner-michael     70 posts (WA-5)
    barragn-nanette      1,194 posts (CA-44)

This is a backfill-only path. The daily collector still reads HTML;
WP-JSON adds depth, not freshness.

Usage:
    python -m pipeline.scripts.backfill_house_wp_json
    python -m pipeline.scripts.backfill_house_wp_json --member jeffries-hakeem
    python -m pipeline.scripts.backfill_house_wp_json --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import psycopg2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.backfill_wp_json import (  # noqa: E402
    CUTOFF_DATE,
    fetch_page,
    html_to_text,
    load_env,
    normalize_url,
)

# (member_id, official_url base, category_slug)
# category_slug is what we look up to find the WP category ID; for these
# 10 it's consistently "press-releases" (or "press_releases").
MEMBERS: list[tuple[str, str, str]] = [
    ("jeffries-hakeem",       "https://jeffries.house.gov",        "press-releases"),
    ("pressley-ayanna",       "https://pressley.house.gov",        "press-releases"),
    ("brownley-julia",        "https://juliabrownley.house.gov",   "press-releases"),
    ("schweikert-david",      "https://schweikert.house.gov",      "press-releases"),
    ("buchanan-vern",         "https://buchanan.house.gov",        "press-releases"),
    ("kiggans-jennifer",      "https://kiggans.house.gov",         "press-releases"),
    ("goodlander-maggie",     "https://goodlander.house.gov",      "press-releases"),
    ("crane-elijah",          "https://crane.house.gov",           "press-releases"),
    ("baumgartner-michael",   "https://baumgartner.house.gov",     "press-releases"),
    ("barragn-nanette",       "https://barragan.house.gov",        "press-releases"),
]

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json,text/javascript,*/*;q=0.01",
}


SLUG_CANDIDATES = (
    "press-releases",
    "press-release",      # Jeffries-style: hyphen + singular
    "press_releases",
    "press_release",
    "press",
    "news",
    "newsroom",
    "congress_press_release",
)


def find_category_id(client: httpx.Client, base: str, slug: str) -> int | None:
    """Look up WP category ID. Try the requested slug first, then a series
    of common variants (singular vs plural, hyphen vs underscore, plus
    the more generic 'news' / 'newsroom'). Some House WP installs use
    different slug conventions; this widens the search before falling
    through to a paginated list of all categories.
    """
    url = f"{base}/wp-json/wp/v2/categories"
    candidates = (slug, *[c for c in SLUG_CANDIDATES if c != slug])

    for candidate in candidates:
        try:
            r = client.get(url, params={"slug": candidate, "per_page": 5}, timeout=15.0)
            if r.status_code == 200:
                arr = r.json()
                if arr:
                    return arr[0]["id"]
        except Exception:
            continue

    # Last resort: list all categories, take the largest one whose slug
    # contains "press" or "news".
    try:
        r = client.get(url, params={"per_page": 100}, timeout=15.0)
        if r.status_code == 200:
            arr = r.json()
            best = None
            for c in arr:
                cs = (c.get("slug") or "").lower()
                if any(tok in cs for tok in ("press", "release", "news", "media")):
                    if best is None or c.get("count", 0) > best.get("count", 0):
                        best = c
            if best:
                return best["id"]
    except Exception as e:
        print(f"  category list error: {e}")
    return None


def fetch_posts(client: httpx.Client, base: str, category_id: int) -> list[dict]:
    """Walk all pages of /wp-json/wp/v2/posts?categories=N. Stops on cutoff."""
    url = f"{base}/wp-json/wp/v2/posts"
    out: list[dict] = []
    page = 1
    while True:
        params = {
            "categories": category_id,
            "per_page": 100,
            "page": page,
            "_fields": "id,date,date_gmt,modified,modified_gmt,link,title,content,excerpt,slug",
        }
        try:
            resp, payload = fetch_page(client, url, params)
        except Exception as e:
            print(f"  page {page}: error {e}")
            break
        if resp is None or resp.status_code != 200:
            break
        if not payload:
            break
        out.extend(payload)
        # WP returns X-WP-TotalPages
        total_pages = int(resp.headers.get("X-WP-TotalPages", "0") or "0")
        if total_pages and page >= total_pages:
            break
        # Safety: stop if a page returned fewer than per_page
        if len(payload) < 100:
            break
        page += 1
        # Stop walking once we're clearly past the cutoff (last item's date older
        # than CUTOFF_DATE). Pagination is newest-first.
        last = payload[-1]
        last_date = last.get("date") or last.get("date_gmt") or ""
        if last_date and last_date[:10] < CUTOFF_DATE.isoformat():
            break
        time.sleep(0.2)
    return out


def insert_post(conn, member_id: str, post: dict, run_id: str) -> bool:
    """Insert a single WP post. Returns True if newly inserted."""
    title_html = (post.get("title") or {}).get("rendered") or ""
    title = html_to_text(title_html).strip()
    if not title or len(title) < 3:
        return False
    body_html = (post.get("content") or {}).get("rendered") or ""
    body_text = html_to_text(body_html).strip()
    excerpt = html_to_text((post.get("excerpt") or {}).get("rendered") or "")
    if not body_text:
        body_text = excerpt
    date_str = post.get("date_gmt") or post.get("date")
    if not date_str:
        return False
    try:
        # WP returns local time without TZ on `date`; UTC on `date_gmt`. Tag UTC.
        pub_dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except Exception:
        return False
    if pub_dt.date() < CUTOFF_DATE:
        return False
    source_url = normalize_url(post.get("link") or "")
    if not source_url or ".house.gov" not in source_url:
        return False

    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO official_site_items
              (official_id, title, published_at, body_text, source_url,
               scrape_run, content_type, date_source, date_confidence)
            VALUES (%s, %s, %s, %s, %s, %s, 'press_release', 'wp_json', 0.95)
            ON CONFLICT (source_url) DO NOTHING
            """,
            (member_id, title, pub_dt, body_text, source_url, run_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()


def collect_member(conn, client, member_id, base, slug, dry_run) -> dict:
    counts = {"posts_seen": 0, "inserted": 0, "skipped_pre_cutoff": 0,
              "skipped_existing": 0, "skipped_bad_field": 0}
    print(f"\n[{member_id}] {base}")
    cat_id = find_category_id(client, base, slug)
    if cat_id is None:
        print(f"  no category id for slug={slug}")
        return counts
    print(f"  category id: {cat_id}")
    posts = fetch_posts(client, base, cat_id)
    print(f"  {len(posts)} posts retrieved from WP-JSON")
    counts["posts_seen"] = len(posts)

    if dry_run:
        for p in posts[:3]:
            t = html_to_text((p.get("title") or {}).get("rendered") or "")
            print(f"    {p.get('date','')[:10]} | {t[:75]}")
        return counts

    run_id = f"wpjson-{member_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    cur = conn.cursor()
    cur.execute("INSERT INTO scrape_runs (id, run_type) VALUES (%s, 'backfill')", (run_id,))
    conn.commit()
    cur.close()

    for p in posts:
        # Cutoff filter
        date_str = p.get("date_gmt") or p.get("date") or ""
        if date_str[:10] < CUTOFF_DATE.isoformat():
            counts["skipped_pre_cutoff"] += 1
            continue
        if insert_post(conn, member_id, p, run_id):
            counts["inserted"] += 1
        else:
            counts["skipped_existing"] += 1

    cur = conn.cursor()
    import json as _json
    cur.execute(
        "UPDATE scrape_runs SET finished_at = NOW(), stats = %s::jsonb WHERE id = %s",
        (_json.dumps(counts), run_id),
    )
    conn.commit()
    cur.close()
    print(f"  result: {counts}")
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--member", help="Run only one member_id")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load_env()
    members = MEMBERS
    if args.member:
        members = [m for m in MEMBERS if m[0] == args.member]
    if not members:
        print("no matching members"); return
    conn = None if args.dry_run else psycopg2.connect(os.environ["DATABASE_URL"])
    grand = {"posts_seen": 0, "inserted": 0, "skipped_pre_cutoff": 0,
             "skipped_existing": 0, "skipped_bad_field": 0}
    with httpx.Client(timeout=20.0, headers=HEADERS, follow_redirects=True) as client:
        for member_id, base, slug in members:
            counts = collect_member(conn, client, member_id, base, slug, args.dry_run)
            for k in grand:
                grand[k] += counts.get(k, 0)
    if conn:
        conn.close()
    print(f"\nGRAND TOTAL: {grand}")


if __name__ == "__main__":
    main()
