"""Pull Rand Paul's op-eds from his WP REST custom post type.

Paul's seed only collects from `/news/` (press releases). His op-eds live
on a separate listing at `/news-old/op-eds/`, exposed via WP-JSON at
`/wp-json/wp/v2/op_eds`. As of 2026-04-25 there are 241 total since 2016.

Two complications, both inherited from a 2026-03-02 site migration:
  1. Items dated 2026-03-02T14:26:* are re-stamped migration entries; the
     `date` field there is the migration timestamp, not real publication.
  2. ~half of those stamped items are duplicates of older op-eds whose
     real-dated originals are still in the same response (their slug ends
     with -2/-3/etc -- the numeric suffix is the WP "this slug already
     existed" marker).

Strategy:
  - Pull /wp-json/wp/v2/op_eds?after=2025-01-01T00:00:00 (server-side filter).
  - For records NOT in the migration-stamp window: insert with date_source
    'wp_json' and confidence 1.0.
  - For records IN the migration-stamp window:
      * skip slugs ending in `-{N}` (duplicate of a real-dated original)
      * keep unsuffixed slugs as op_ed with date_source 'wp_modified_migration'
        and confidence 0.3 -- title/body are real, only the date is suspect.

Usage:
    python -m pipeline.scripts.backfill_paul_op_eds [--dry-run]
"""
import argparse
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import psycopg2
from bs4 import BeautifulSoup

from pipeline.backfill_wp_json import fetch_all, html_to_text, load_env, normalize_url

SENATOR_ID = "paul-rand"
BASE_URL = "https://www.paul.senate.gov"
ENDPOINT = "op_eds"
CUTOFF = date(2025, 1, 1)

# Items dated 2026-03-02 with date == modified (within a minute) are
# re-stamped migration entries; their date field is the migration timestamp,
# not real publication. Real op-eds have modified > date by hours/days.
MIGRATION_DATE_PREFIX = "2026-03-02"

NUMBERED_SUFFIX = re.compile(r"-\d+$")


def is_migration_stamped(rec: dict) -> bool:
    date_iso = rec.get("date_gmt") or rec.get("date") or ""
    mod_iso = rec.get("modified_gmt") or rec.get("modified") or ""
    if not date_iso.startswith(MIGRATION_DATE_PREFIX):
        return False
    try:
        d = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
        m = datetime.fromisoformat(mod_iso.replace("Z", "+00:00"))
    except ValueError:
        return True
    return abs((m - d).total_seconds()) < 120


def is_numbered_duplicate(slug: str) -> bool:
    return bool(NUMBERED_SUFFIX.search(slug))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    args = ap.parse_args()

    load_env()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    print(f"Fetching op-eds for {SENATOR_ID} via WP-JSON...")
    records = fetch_all(
        BASE_URL,
        ENDPOINT,
        extra_params={"after": "2025-01-01T00:00:00"},
    )
    print(f"Total fetched: {len(records)}")

    run_id = f"oped-paul-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    if not args.dry_run:
        cur = conn.cursor()
        cur.execute("INSERT INTO scrape_runs (id, run_type) VALUES (%s, 'backfill')", (run_id,))
        conn.commit()
        cur.close()

    counts = {"inserted_real": 0, "inserted_migration": 0,
              "skipped_dup": 0, "skipped_existing": 0, "skipped_pre_cutoff": 0}

    for rec in records:
        link = rec.get("link")
        if not link:
            continue
        source_url = normalize_url(link)
        slug = rec.get("slug", "")
        date_str = rec.get("date_gmt") or rec.get("date")
        if not date_str:
            continue

        try:
            pub_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        if pub_dt.date() < CUTOFF:
            counts["skipped_pre_cutoff"] += 1
            continue

        stamped = is_migration_stamped(rec)
        if stamped and is_numbered_duplicate(slug):
            counts["skipped_dup"] += 1
            continue

        date_source = "wp_modified_migration" if stamped else "wp_json"
        date_confidence = 0.3 if stamped else 1.0

        title_raw = rec.get("title", {})
        title = title_raw.get("rendered") if isinstance(title_raw, dict) else (title_raw or "")
        title = BeautifulSoup(title or "", "lxml").get_text(strip=True)
        if len(title) < 5:
            continue

        content_raw = rec.get("content", {})
        content_html = content_raw.get("rendered") if isinstance(content_raw, dict) else ""
        body_text = html_to_text(content_html)

        if args.dry_run:
            tag = "MIGR" if stamped else "REAL"
            print(f"  [{tag} conf={date_confidence}] {pub_dt.date()} | {title[:75]}")
            continue

        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO press_releases
                  (senator_id, title, published_at, body_text, source_url,
                   scrape_run, content_type, date_source, date_confidence)
                VALUES (%s, %s, %s, %s, %s, %s, 'op_ed', %s, %s)
                ON CONFLICT (source_url) DO NOTHING
                """,
                (SENATOR_ID, title, pub_dt, body_text or None, source_url,
                 run_id, date_source, date_confidence),
            )
            conn.commit()
            if cur.rowcount > 0:
                key = "inserted_migration" if stamped else "inserted_real"
                counts[key] += 1
            else:
                counts["skipped_existing"] += 1
        except Exception as e:
            conn.rollback()
            print(f"  ERR on {source_url}: {e}")
        finally:
            cur.close()

    if not args.dry_run:
        cur = conn.cursor()
        import json as _json
        cur.execute(
            "UPDATE scrape_runs SET finished_at = NOW(), stats = %s::jsonb WHERE id = %s",
            (_json.dumps(counts), run_id),
        )
        conn.commit()
        cur.close()

    print(f"\nDone: {counts}")
    conn.close()


if __name__ == "__main__":
    main()
