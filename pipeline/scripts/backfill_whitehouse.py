"""Backfill White House content from Jan 1, 2025 to present.

One-off crawl over the three WH streams (/releases/, /briefings-statements/,
/presidential-actions/). Uses the existing WhitehouseCollector with a deep
pagination budget. Dedup is handled by ON CONFLICT (source_url).

Usage:
    python -m pipeline.scripts.backfill_whitehouse
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from pipeline.collectors.whitehouse_collector import WhitehouseCollector
from pipeline.lib.identity import normalize_url
from pipeline.lib.seeds import load_members

_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"\''))

DB_URL = os.environ["DATABASE_URL"]
log = logging.getLogger("capitol.backfill.whitehouse")


def insert_release(conn, rec, run_id: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO press_releases
                (senator_id, title, published_at, body_text, source_url,
                 raw_html, content_type, date_source, date_confidence,
                 content_hash, scrape_run, scraped_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (source_url) DO NOTHING
            """,
            (
                rec.senator_id,
                rec.title,
                rec.published_at,
                rec.body_text or None,
                normalize_url(rec.source_url),
                rec.raw_html or None,
                rec.content_type,
                rec.date_source or None,
                rec.date_confidence or None,
                rec.content_hash or None,
                run_id,
            ),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        log.error("Insert failed for %s: %s", rec.source_url, e)
        return False
    finally:
        cur.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--since", default="2025-01-01")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    run_id = f"backfill-whitehouse-{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M')}"

    members = load_members()
    wh = next((m for m in members if m["senator_id"] == "whitehouse"), None)
    if not wh:
        print("ERROR: whitehouse entry not found in seeds")
        sys.exit(1)

    print(f"Starting backfill. since={args.since}, max_pages={args.max_pages}")
    collector = WhitehouseCollector()
    result = await collector.collect(wh, since=since, max_pages=args.max_pages)

    print(
        f"Collected {len(result.releases)} records across {result.pages_scraped} pages"
        f" in {result.duration_seconds:.1f}s"
    )
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for e in result.errors[:20]:
            print("  ", e)

    if args.dry_run:
        by_type: dict[str, int] = {}
        for r in result.releases:
            by_type[r.content_type] = by_type.get(r.content_type, 0) + 1
        print("dry-run breakdown:", by_type)
        return

    conn = psycopg2.connect(DB_URL)
    new_count = 0
    for rec in result.releases:
        if insert_release(conn, rec, run_id):
            new_count += 1
    conn.close()
    print(f"Inserted {new_count} new records (skipped {len(result.releases) - new_count} dupes)")


if __name__ == "__main__":
    asyncio.run(main())
