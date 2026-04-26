"""Custom-scraper backfill for non-WP silos surfaced by silo_verify.

For each (senator_id, section_url, content_type) silo, walks the section's
listing pages using the same selector cascade that backfill.py uses for
press releases, then writes records into press_releases with the right
content_type and date_source='silo_backfill'.

The 9 silos targeted here were verified by silo_verify.py to have at
least 5 confirmed in-window items.

Usage:
    python -m pipeline.scripts.backfill_silos              # all silos
    python -m pipeline.scripts.backfill_silos --senator cotton-tom
    python -m pipeline.scripts.backfill_silos --dry-run
    python -m pipeline.scripts.backfill_silos --max-pages 3
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import psycopg2
from bs4 import BeautifulSoup

from pipeline.backfill import (
    extract_listing_items,
    extract_item_data,
    extract_body_text,
    find_next_page,
    parse_date,
)
from pipeline.backfill_wp_json import load_env, normalize_url

CUTOFF = date(2025, 1, 1)

# (senator_id, section_url, content_type)
# Verified active by silo_verify.py 2026-04-25 — see docs/silo_action_plan.md
SILOS: list[tuple[str, str, str]] = [
    ("crapo-mike", "https://www.crapo.senate.gov/media/columns/", "op_ed"),
    ("crapo-mike", "https://www.crapo.senate.gov/media/newsletters/", "blog"),
    ("ernst-joni", "https://www.ernst.senate.gov/news/columns/", "op_ed"),
    ("cramer-kevin", "https://www.cramer.senate.gov/news/newsletter-archive/", "blog"),
    ("reed-jack", "https://www.reed.senate.gov/news/speeches/", "floor_statement"),
    ("cotton-tom", "https://www.cotton.senate.gov/news/speeches/", "floor_statement"),
    ("grassley-chuck", "https://www.grassley.senate.gov/news/remarks/", "floor_statement"),
    ("warren-elizabeth", "https://www.warren.senate.gov/newsroom/op-eds/", "op_ed"),
    ("warren-elizabeth", "https://www.warren.senate.gov/oversight/reports/", "letter"),
]

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def load_seed_selectors(senator_id: str) -> dict:
    seeds = json.loads(
        (Path(__file__).resolve().parents[1] / "seeds" / "senate.json").read_text()
    )["members"]
    for s in seeds:
        if s["senator_id"] == senator_id:
            return s.get("selectors") or {}
    return {}


def collect_silo(
    conn,
    client: httpx.Client,
    senator_id: str,
    section_url: str,
    content_type: str,
    selectors: dict,
    max_pages: int,
    dry_run: bool,
) -> dict:
    print(f"\n[{senator_id}] {section_url}  ({content_type})")
    counts = {
        "pages_walked": 0,
        "items_seen": 0,
        "inserted": 0,
        "skipped_existing": 0,
        "skipped_pre_cutoff": 0,
        "skipped_no_date": 0,
        "skipped_short": 0,
        "skipped_non_gov": 0,
    }

    run_id = f"silo-{senator_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    if not dry_run:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO scrape_runs (id, run_type) VALUES (%s, 'backfill')", (run_id,)
        )
        conn.commit()
        cur.close()

    current = section_url
    page = 0
    seen_urls: set[str] = set()
    while current and page < max_pages:
        page += 1
        try:
            r = client.get(current, follow_redirects=True)
        except Exception as e:
            print(f"  page {page} fetch err: {e}")
            break
        if r.status_code != 200:
            print(f"  page {page} status {r.status_code}")
            break
        soup = BeautifulSoup(r.text, "lxml")
        items = extract_listing_items(soup, selectors)
        if not items:
            print(f"  page {page}: no items found (selectors may not match)")
            break
        print(f"  page {page}: {len(items)} items")
        counts["pages_walked"] += 1

        for it in items:
            counts["items_seen"] += 1
            try:
                title, date_text, detail = extract_item_data(it, section_url, selectors)
            except Exception:
                continue
            title = (title or "").strip()
            date_text = (date_text or "").strip()
            detail = (detail or "").strip()
            if not detail or not title or len(title) < 5:
                counts["skipped_short"] += 1
                continue
            detail = normalize_url(detail)
            if detail in seen_urls:
                continue
            seen_urls.add(detail)
            if ".senate.gov" not in detail:
                counts["skipped_non_gov"] = counts.get("skipped_non_gov", 0) + 1
                continue

            pub_dt = parse_date(date_text) if date_text else None
            if not pub_dt:
                counts["skipped_no_date"] += 1
                continue
            if isinstance(pub_dt, date) and not isinstance(pub_dt, datetime):
                pub_dt = datetime.combine(pub_dt, datetime.min.time(), tzinfo=timezone.utc)
            if pub_dt.date() < CUTOFF:
                counts["skipped_pre_cutoff"] += 1
                continue

            if dry_run:
                print(f"    {pub_dt.date()} | {title[:80]}")
                continue

            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO press_releases
                      (senator_id, title, published_at, source_url,
                       scrape_run, content_type, date_source, date_confidence)
                    VALUES (%s, %s, %s, %s, %s, %s, 'silo_backfill', 0.9)
                    ON CONFLICT (source_url) DO NOTHING
                    """,
                    (senator_id, title, pub_dt, detail, run_id, content_type),
                )
                conn.commit()
                if cur.rowcount > 0:
                    counts["inserted"] += 1
                else:
                    counts["skipped_existing"] += 1
            except Exception as e:
                conn.rollback()
                print(f"    ERR on {detail}: {e}")
            finally:
                cur.close()

        nxt = find_next_page(soup, current)
        if not nxt or nxt == current:
            break
        current = nxt

    if not dry_run:
        cur = conn.cursor()
        cur.execute(
            "UPDATE scrape_runs SET finished_at = NOW(), stats = %s::jsonb WHERE id = %s",
            (json.dumps(counts), run_id),
        )
        conn.commit()
        cur.close()

    print(f"  result: {counts}")
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--senator", help="Run only for one senator_id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-pages", type=int, default=10)
    args = ap.parse_args()

    load_env()

    silos = SILOS
    if args.senator:
        silos = [s for s in silos if s[0] == args.senator]
    if not silos:
        print("no matching silos")
        return

    conn = None if args.dry_run else psycopg2.connect(os.environ["DATABASE_URL"])
    headers = {"User-Agent": UA}

    grand = {
        "items_seen": 0, "inserted": 0,
        "skipped_existing": 0, "skipped_pre_cutoff": 0,
        "skipped_no_date": 0, "skipped_short": 0,
        "skipped_non_gov": 0,
    }
    with httpx.Client(timeout=20.0, headers=headers) as client:
        for sid, url, ct in silos:
            sels = load_seed_selectors(sid)
            counts = collect_silo(
                conn, client, sid, url, ct, sels, args.max_pages, args.dry_run
            )
            for k in grand:
                grand[k] += counts.get(k, 0)

    if conn:
        conn.close()
    print(f"\nGRAND TOTAL: {grand}")


if __name__ == "__main__":
    main()
