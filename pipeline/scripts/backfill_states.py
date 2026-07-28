"""Deep-walk state collectors to close back-coverage gaps.

The daily updater fetches page 1 only -- correct for a daily run, wrong
for first-time coverage. A source seeded after its archive already ran
deep therefore lands TRUNCATED: `pipeline back-coverage` on 2026-07-28
reported 61 truncated state sources, worst in California (25) and
Nebraska (14). Shane Wilkin's Ohio page offers 31 items and we had 3.

This walks the same registry collectors with real pagination and upserts
through the same `upsert_release` the daily run uses, so provenance,
content versioning and dedup behave identically. It is a backfill, not a
second collection path.

Usage:
    python -m pipeline.scripts.backfill_states --jurisdiction ca --max-pages 10
    python -m pipeline.scripts.backfill_states --jurisdiction ca ne oh
    python -m pipeline.scripts.backfill_states --only oh-senate-wilkin
    python -m pipeline.scripts.backfill_states --jurisdiction ca --dry-run
"""

import argparse
import asyncio
import logging
import os
import sys
from collections import Counter

import psycopg2
from dotenv import load_dotenv

from pipeline.collectors.registry import CollectorRegistry
from pipeline.commands.update import upsert_release
from pipeline.lib.seeds import load_members

load_dotenv(".env.local")
log = logging.getLogger("capitol.backfill_states")

# Jurisdictions with collectors that actually run. 'us' is excluded on
# purpose: the federal tier has its own backfill paths (backfill.py,
# backfill_playwright.py, the silo scripts) with per-CMS handling this
# generic walker does not replicate.
DEFAULT_JURISDICTIONS = ["ca", "co", "mo", "ne", "oh", "tx", "wv"]

# Concurrency is per-source. State sites are small government hosts, and
# several share one origin (all 33 Ohio senators sit on ohiosenate.gov),
# so this stays well below the federal collector's default.
DEFAULT_CONCURRENCY = 3


async def _collect_one(sem, registry, member, max_pages, dry_run, conn, totals):
    async with sem:
        sid = member["official_id"]
        collector = registry.get_collector(member)
        try:
            result = await collector.collect(member, since=None, max_pages=max_pages)
        except Exception as e:
            totals["errored"] += 1
            print(f"{sid:28} ERROR {type(e).__name__}: {e}", flush=True)
            return

        new = updated = 0
        if not dry_run:
            for release in result.releases:
                if not release.title or not release.source_url:
                    continue
                is_new, was_updated = upsert_release(conn, release)
                new += int(is_new)
                updated += int(was_updated)

        totals["sources"] += 1
        totals["collected"] += len(result.releases)
        totals["new"] += new
        totals["updated"] += updated
        flag = " ERR" if result.errors else ""
        # flush: a full-corpus walk runs for the better part of an hour,
        # and Python block-buffers stdout when it is a pipe rather than a
        # TTY. Without this the operator sees nothing at all until the
        # process exits, which is indistinguishable from a hang.
        print(f"{sid:28} collected={len(result.releases):4} new={new:4} "
              f"updated={updated:3}{flag} {result.errors[:1] if result.errors else ''}",
              flush=True)


async def run(jurisdictions, only, max_pages, dry_run, concurrency):
    members = load_members(jurisdictions=jurisdictions)
    # Caucus pressrooms are collection sources; identity-only roster rows
    # are not, and load_members already drops those (collection_method None).
    if only:
        members = [m for m in members if any(o in m["official_id"] for o in only)]
    if not members:
        sys.exit("No matching state sources")

    print(f"Backfilling {len(members)} sources, max_pages={max_pages}"
          f"{' (DRY RUN)' if dry_run else ''}\n", flush=True)

    registry = CollectorRegistry()
    sem = asyncio.Semaphore(concurrency)
    totals = Counter()
    conn = None if dry_run else psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        await asyncio.gather(*[
            _collect_one(sem, registry, m, max_pages, dry_run, conn, totals)
            for m in members
        ])
    finally:
        if conn:
            conn.close()

    print(f"\nTOTAL sources={totals['sources']} collected={totals['collected']} "
          f"new={totals['new']} updated={totals['updated']} errored={totals['errored']}")


def main():
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jurisdiction", nargs="*", default=DEFAULT_JURISDICTIONS)
    p.add_argument("--only", nargs="*", help="substring filter on official_id")
    p.add_argument("--max-pages", type=int, default=10)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    a = p.parse_args()
    asyncio.run(run(a.jurisdiction, a.only, a.max_pages, a.dry_run, a.concurrency))


if __name__ == "__main__":
    main()
