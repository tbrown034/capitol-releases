"""Collect the Colorado caucus corpus and attribute it to legislators.

Two phases, runnable independently:

  collect    walk the four caucus sources and upsert items
  attribute  (re-)run named-entity attribution over stored Colorado items
             and rewrite item_mentions

Attribution is a separate phase on purpose. It reads stored body text
rather than live pages, so improving a matching rule means re-running one
cheap pass over the database instead of re-scraping four websites.

Usage:
    python -m pipeline.scripts.backfill_colorado collect --max-pages 40
    python -m pipeline.scripts.backfill_colorado attribute
    python -m pipeline.scripts.backfill_colorado attribute --dry-run
"""

import argparse
import asyncio
import logging
import os
import sys
from collections import Counter

import psycopg2
from dotenv import load_dotenv

from pipeline.collectors.co_caucus_collectors import normalized_title_key
from pipeline.collectors.registry import CollectorRegistry
from pipeline.commands.update import upsert_release
from pipeline.lib.co_attribution import ColoradoAttributor
from pipeline.lib.seeds import load_members

load_dotenv(".env.local")
log = logging.getLogger("capitol.backfill_colorado")

CAUCUS_OFFICE_TYPE = "caucus_pressroom"


def _connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    return psycopg2.connect(url)


def caucus_sources() -> list[dict]:
    return [
        m for m in load_members(jurisdictions=["co"])
        if m.get("office_type") == CAUCUS_OFFICE_TYPE
    ]


async def collect(max_pages: int, only: str | None) -> None:
    sources = caucus_sources()
    if only:
        sources = [s for s in sources if only in s["official_id"]]
    if not sources:
        sys.exit("No matching Colorado caucus sources")

    registry = CollectorRegistry()
    conn = _connect()
    totals = Counter()

    try:
        for source in sources:
            collector = registry.get_collector(source)
            result = await collector.collect(source, since=None, max_pages=max_pages)

            new = updated = 0
            for release in result.releases:
                if not release.title or not release.source_url:
                    continue
                is_new, was_updated = upsert_release(conn, release)
                new += int(is_new)
                updated += int(was_updated)

            totals["collected"] += len(result.releases)
            totals["new"] += new
            totals["updated"] += updated
            print(f"{source['official_id']:24} collected={len(result.releases):4} "
                  f"new={new:4} updated={updated:3} errors={result.errors[:1]}")
    finally:
        conn.close()

    print(f"\nTOTAL collected={totals['collected']} new={totals['new']} "
          f"updated={totals['updated']}")


def attribute(dry_run: bool) -> None:
    attributor = ColoradoAttributor()
    known = {legislator.official_id for legislator in attributor.roster}
    conn = _connect()
    cur = conn.cursor()

    # Only caucus-published items need this pass. A Colorado legislator with
    # a personal pressroom would attribute to themselves at collection time.
    cur.execute(
        """
        SELECT i.id, i.title, i.body_text
        FROM official_site_items i
        JOIN officials o ON o.id = i.official_id
        WHERE o.jurisdiction = 'co'
          AND o.office_type = %s
          AND i.deleted_at IS NULL
        """,
        (CAUCUS_OFFICE_TYPE,),
    )
    rows = cur.fetchall()
    print(f"Attributing {len(rows)} Colorado caucus items...")

    stats = Counter()
    unresolved = Counter()
    pending: list[tuple] = []

    for item_id, title, body_text in rows:
        mentions = attributor.attribute(title or "", body_text or "")
        for surname in attributor.ambiguous_matches(body_text or ""):
            unresolved[surname] += 1
        if not mentions:
            stats["items_with_no_mention"] += 1
            continue
        stats["items_with_mentions"] += 1
        for mention in mentions:
            # Guard the FK: a roster entry that never synced would abort the
            # whole batch on insert.
            if mention.official_id not in known:
                stats["skipped_unknown_official"] += 1
                continue
            stats[mention.role] += 1
            pending.append((
                item_id, mention.official_id, mention.role,
                mention.match_method, mention.matched_text[:500], mention.confidence,
            ))

    if dry_run:
        print("\nDRY RUN -- no writes")
    else:
        # Full rebuild: attribution is derived data, so the rules that
        # produced the old rows are gone the moment this module changes.
        cur.execute(
            """
            DELETE FROM item_mentions
            WHERE item_id IN (
                SELECT i.id FROM official_site_items i
                JOIN officials o ON o.id = i.official_id
                WHERE o.jurisdiction = 'co' AND o.office_type = %s
            )
            """,
            (CAUCUS_OFFICE_TYPE,),
        )
        cur.executemany(
            """
            INSERT INTO item_mentions
                (item_id, official_id, role, match_method, matched_text, confidence)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (item_id, official_id, role) DO NOTHING
            """,
            pending,
        )
        conn.commit()
        print(f"\nWrote {len(pending)} mention rows")

    print(f"  items with mentions:    {stats['items_with_mentions']}")
    print(f"  items with none:        {stats['items_with_no_mention']}")
    print(f"  primary / quoted / mentioned: "
          f"{stats['primary']} / {stats['quoted']} / {stats['mentioned']}")
    if stats["skipped_unknown_official"]:
        print(f"  skipped (not in roster): {stats['skipped_unknown_official']}")
    if unresolved:
        print(f"  unresolved shared surnames: {dict(unresolved.most_common(5))}")

    conn.close()


def report() -> None:
    """Print the per-legislator leaderboard the mentions table enables."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT o.full_name, o.party, o.chamber, o.district,
               COUNT(*) FILTER (WHERE m.role = 'quoted')    AS quoted,
               COUNT(*) FILTER (WHERE m.role = 'primary')   AS headlined,
               COUNT(*) FILTER (WHERE m.role = 'mentioned') AS mentioned
        FROM item_mentions m
        JOIN officials o ON o.id = m.official_id
        GROUP BY o.full_name, o.party, o.chamber, o.district
        ORDER BY quoted DESC, mentioned DESC
        LIMIT 20
        """
    )
    print(f"\n{'legislator':26} {'party':6} {'seat':8} {'quoted':>7} "
          f"{'headlined':>10} {'mentioned':>10}")
    for name, party, chamber, district, quoted, headlined, mentioned in cur.fetchall():
        seat = f"{(chamber or '')[:3].upper()}-{district}"
        print(f"{name[:25]:26} {party or '?':6} {seat:8} {quoted:7} "
              f"{headlined:10} {mentioned:10}")
    conn.close()


def main() -> None:
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["collect", "attribute", "report"])
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--only", help="substring filter on official_id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.phase == "collect":
        asyncio.run(collect(args.max_pages, args.only))
    elif args.phase == "attribute":
        attribute(args.dry_run)
    else:
        report()


if __name__ == "__main__":
    main()
