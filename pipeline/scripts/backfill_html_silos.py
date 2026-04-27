"""Backfill original-content silos that live on senator-specific HTML
listings outside of /press-releases/.

Some senators publish substantial original content (op-eds, columns,
blogs, letters) on dedicated sections of their senate.gov sites that the
seed config never points us at. Recon (`pipeline/recon/content_stream_*`)
flagged these as the largest remaining archival gap (~4.6k records as of
2026-04-27). Their listings use the same CMS markup as the
`/press-releases/` sections we already scrape, so the existing
`extract_listing_items` + `find_next_page` waterfall does the heavy
lifting; this script just walks an explicit URL list and tags records
with the right content_type at insert time.

Usage:
    python -m pipeline.scripts.backfill_html_silos                # all configured silos
    python -m pipeline.scripts.backfill_html_silos --senator grassley-chuck
    python -m pipeline.scripts.backfill_html_silos --dry-run
    python -m pipeline.scripts.backfill_html_silos --max-pages 5  # cap per silo

Each entry below maps to one HTML listing section. Add new silos here as
recon surfaces them. When `additional_streams` is added to senate.json
schema, this list becomes the bootstrap; the seed file becomes the
source of truth.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import psycopg2
from bs4 import BeautifulSoup

from pipeline.lib.http import create_client, fetch_with_retry, politeness_delay
from pipeline.lib.identity import normalize_url, content_hash
from pipeline.backfill import (
    extract_listing_items,
    extract_item_data,
    extract_body_text,
    find_next_page,
    parse_date,
)

# Load .env so DATABASE_URL is set when run from the repo root.
_env_path = Path(__file__).resolve().parents[1] / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

CUTOFF = date(2025, 1, 1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("capitol.backfill_html_silos")


# Each silo: (senator_id, listing_url, content_type, date_confidence)
# date_confidence is 0.6 for listing-page extraction (we don't always
# have a per-record date in the markup; falls back to URL/text parsing).
#
# Recon (2026-04-27) flagged Crapo /media/columns/ and Warren
# /oversight/letters as op_ed/letter silos but their listing pages
# actually link to /news/in-the-news/ (Crapo) and /newsroom/press-releases/
# (Warren) -- press-release wrappers and third-party clippings, both out
# of scope per CLAUDE.md. They were dropped from this list and need a
# different listing URL before they can be safely silo-collected.
SILOS: list[tuple[str, str, str, float]] = [
    ("grassley-chuck",   "https://www.grassley.senate.gov/news/commentary/", "op_ed", 0.6),
    ("ernst-joni",       "https://www.ernst.senate.gov/news/columns/",       "op_ed", 0.6),
    ("heinrich-martin",  "https://www.heinrich.senate.gov/newsroom/blog",    "blog",  0.6),
]


async def collect_silo(
    conn,
    senator_id: str,
    listing_url: str,
    content_type: str,
    date_confidence: float,
    max_pages: int,
    dry_run: bool,
) -> dict:
    """Walk one HTML listing all the way back, inserting in-window records."""
    run_id = f"silo-{senator_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    if not dry_run:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO scrape_runs (id, run_type) VALUES (%s, 'backfill') ON CONFLICT DO NOTHING",
            (run_id,),
        )
        conn.commit()
        cur.close()

    counts = {
        "fetched": 0,
        "inserted": 0,
        "skipped_existing": 0,
        "skipped_pre_cutoff": 0,
        "skipped_no_date": 0,
        "skipped_short_body": 0,
        "skipped_out_of_section": 0,
        "errors": 0,
    }

    log.info("[%s] %s -> %s", senator_id, listing_url, content_type)
    # Safety prefix: only insert detail URLs that live under the silo's
    # own path. This defends against listings that surface press-release
    # wrappers or "in the news" clippings (Crapo/Warren patterns from
    # 2026-04-27 recon).
    listing_prefix = urlparse(listing_url).path.rstrip("/")

    async with create_client() as client:
        current_url = listing_url
        page = 0

        while current_url and page < max_pages:
            page += 1
            try:
                resp = await fetch_with_retry(client, current_url)
            except Exception as e:
                log.warning("page %d fetch failed: %s", page, e)
                counts["errors"] += 1
                break

            if resp.status_code != 200:
                log.warning("page %d returned HTTP %d", page, resp.status_code)
                counts["errors"] += 1
                break

            soup = BeautifulSoup(resp.text, "lxml")
            items = extract_listing_items(soup, {})
            if not items:
                log.warning("page %d: no items found", page)
                break

            log.info("  page %d: %d items", page, len(items))
            page_in_window = 0

            for item in items:
                counts["fetched"] += 1
                title, date_text, detail_url = extract_item_data(item, current_url, {})
                if not detail_url:
                    continue
                detail_url = normalize_url(detail_url)
                pub_date = parse_date(date_text) if date_text else None

                if pub_date and pub_date.date() < CUTOFF:
                    counts["skipped_pre_cutoff"] += 1
                    continue
                if pub_date:
                    page_in_window += 1

                # Section-prefix guard: skip records whose URL doesn't live
                # in the silo's own section. Catches listings that mix
                # external clippings or press-release wrappers.
                detail_path = urlparse(detail_url).path
                if listing_prefix and not detail_path.startswith(listing_prefix):
                    counts["skipped_out_of_section"] = counts.get("skipped_out_of_section", 0) + 1
                    continue

                if not pub_date:
                    counts["skipped_no_date"] += 1
                    continue

                # Dedup against existing rows
                if conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT 1 FROM press_releases WHERE source_url = %s",
                        (detail_url,),
                    )
                    exists = cur.fetchone() is not None
                    cur.close()
                    if exists:
                        counts["skipped_existing"] += 1
                        continue

                # Fetch detail page for body text
                body_text = ""
                try:
                    detail_resp = await client.get(detail_url, follow_redirects=True)
                    await politeness_delay(0.3)
                    if detail_resp.status_code == 200:
                        detail_soup = BeautifulSoup(detail_resp.text, "lxml")
                        body_text = extract_body_text(detail_soup)
                except Exception as e:
                    log.warning("detail fetch failed for %s: %s: %s", detail_url, type(e).__name__, e)
                    counts["errors"] += 1

                if len(body_text) < 200:
                    counts["skipped_short_body"] += 1
                    continue

                if dry_run:
                    counts["inserted"] += 1
                    log.info("    [DRY] +%s | %s", pub_date.strftime("%Y-%m-%d"), title[:70])
                    continue

                cur = conn.cursor()
                try:
                    cur.execute(
                        """
                        INSERT INTO press_releases
                            (senator_id, title, published_at, body_text,
                             source_url, content_type, date_source,
                             date_confidence, content_hash, scrape_run, scraped_at, last_seen_live)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (source_url) DO NOTHING
                        """,
                        (
                            senator_id,
                            title,
                            pub_date,
                            body_text or None,
                            detail_url,
                            content_type,
                            "listing_page",
                            date_confidence,
                            content_hash(body_text) if body_text else None,
                            run_id,
                        ),
                    )
                    conn.commit()
                    if cur.rowcount > 0:
                        counts["inserted"] += 1
                        log.info("    + %s | %s", pub_date.strftime("%Y-%m-%d"), title[:70])
                    else:
                        counts["skipped_existing"] += 1
                except Exception as e:
                    conn.rollback()
                    log.error("    [ERR] %s: %s", type(e).__name__, e)
                    counts["errors"] += 1
                finally:
                    cur.close()

            # Smart stop: pages are date-descending, so once a page has zero
            # in-window records we've walked past the cutoff and further
            # pagination is wasted requests on the senator's server.
            if page_in_window == 0:
                log.info("  page %d had 0 in-window records; stopping", page)
                break

            current_url = find_next_page(soup, current_url)

    if not dry_run and conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE scrape_runs
            SET finished_at = NOW(), stats = %s
            WHERE id = %s
            """,
            (json.dumps(counts), run_id),
        )
        conn.commit()
        cur.close()

    return counts


async def main():
    parser = argparse.ArgumentParser(description="Backfill HTML content silos")
    parser.add_argument("--senator", help="Only this senator_id")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--max-pages", type=int, default=200, help="Cap per silo (default 200)")
    args = parser.parse_args()

    silos = SILOS
    if args.senator:
        silos = [s for s in SILOS if s[0] == args.senator]
        if not silos:
            print(f"No silo configured for {args.senator}. Known: {[s[0] for s in SILOS]}")
            sys.exit(1)

    db_url = os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(db_url) if (db_url and not args.dry_run) else None

    grand: dict[str, int] = {
        "fetched": 0, "inserted": 0, "skipped_existing": 0,
        "skipped_pre_cutoff": 0, "skipped_no_date": 0,
        "skipped_short_body": 0, "skipped_out_of_section": 0,
        "errors": 0,
    }
    for senator_id, url, ctype, date_conf in silos:
        result = await collect_silo(
            conn, senator_id, url, ctype, date_conf,
            max_pages=args.max_pages, dry_run=args.dry_run,
        )
        for k, v in result.items():
            grand[k] = grand.get(k, 0) + v
        log.info("[%s] %s", senator_id, result)

    if conn:
        conn.close()

    print("\n=== GRAND TOTAL ===")
    for k, v in grand.items():
        print(f"  {k:20s} {v}")


if __name__ == "__main__":
    asyncio.run(main())
