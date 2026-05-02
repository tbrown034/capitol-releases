"""
Sync member rows from pipeline/seeds/*.json into the senators table.

Press_releases.senator_id is a FK to senators(id), so every member row
referenced by the daily collector must exist in the table before
update.py can insert that member's records. The Senate roster has been
hand-loaded historically; this command formalizes that path so adding
House (and future state houses) is a config-and-script step.

Operation:
  - Reads load_members(include_unconfigured=True) — full roster across
    every seed file, including unconfigured House members so a single
    sync makes the entire 437-member House visible to the DB even if
    only 89 currently collect.
  - UPSERTs each member into senators(id, ...) with chamber + district
    + status='active' set from the seed.
  - Updates updated_at on conflict so it's safe to rerun.
  - Never deletes rows. A member who leaves a seed file (rare) stays
    in the DB with status untouched; mark them 'former' through a
    separate path if needed.

Usage:
  python -m pipeline sync-members             # all chambers, dry-run report
  python -m pipeline sync-members --apply     # actually write
  python -m pipeline sync-members --chamber house --apply
"""

import argparse
import logging
import os
import sys

import psycopg2

from pipeline.lib.seeds import load_members


log = logging.getLogger("capitol.sync_members")
DB_URL = os.environ.get("DATABASE_URL")


UPSERT_SQL = """
    INSERT INTO officials (
        id, full_name, party, state, official_url, press_release_url,
        parser_family, requires_js, confidence, last_verified,
        rss_feed_url, collection_method, chamber, district, status,
        scrape_config, branch, jurisdiction, office_type
    ) VALUES (
        %(id)s, %(full_name)s, %(party)s, %(state)s, %(official_url)s,
        %(press_release_url)s, %(parser_family)s, %(requires_js)s,
        %(confidence)s, %(last_verified)s, %(rss_feed_url)s,
        %(collection_method)s, %(chamber)s, %(district)s, 'active',
        %(scrape_config)s::jsonb,
        %(branch)s, %(jurisdiction)s, %(office_type)s
    )
    ON CONFLICT (id) DO UPDATE SET
        full_name         = EXCLUDED.full_name,
        party             = EXCLUDED.party,
        state             = EXCLUDED.state,
        official_url      = EXCLUDED.official_url,
        press_release_url = EXCLUDED.press_release_url,
        parser_family     = EXCLUDED.parser_family,
        requires_js       = EXCLUDED.requires_js,
        confidence        = EXCLUDED.confidence,
        last_verified     = EXCLUDED.last_verified,
        rss_feed_url      = EXCLUDED.rss_feed_url,
        collection_method = EXCLUDED.collection_method,
        chamber           = EXCLUDED.chamber,
        district          = EXCLUDED.district,
        scrape_config     = EXCLUDED.scrape_config,
        branch            = EXCLUDED.branch,
        jurisdiction      = EXCLUDED.jurisdiction,
        office_type       = EXCLUDED.office_type,
        updated_at        = NOW()
"""


def member_to_params(m: dict) -> dict:
    """Coerce a seed member dict into the exact columns senators expects."""
    import json

    selectors = m.get("selectors")
    pagination = m.get("pagination")
    notes = m.get("notes")
    cfg = {}
    if selectors:
        cfg["selectors"] = selectors
    if pagination:
        cfg["pagination"] = pagination
    if notes:
        cfg["notes"] = notes

    return {
        "id": m["senator_id"],
        "full_name": m.get("full_name") or m["senator_id"],
        "party": m.get("party") or "I",
        "state": m.get("state") or "US",
        "official_url": m.get("official_url") or "",
        "press_release_url": m.get("press_release_url"),
        "parser_family": m.get("parser_family"),
        "requires_js": bool(m.get("requires_js", False)),
        "confidence": m.get("confidence"),
        "last_verified": m.get("last_verified"),
        "rss_feed_url": m.get("rss_feed_url"),
        "collection_method": m.get("collection_method"),
        "chamber": m.get("chamber"),  # may be None for executives
        "district": (
            str(m["district"]) if m.get("district") not in (None, "") else None
        ),
        "scrape_config": json.dumps(cfg) if cfg else None,
        # Post-2026-05-02 schema (migration 012). Defaults applied by
        # pipeline.lib.seeds.load_members based on the source seed file.
        "branch": m.get("branch") or "legislative",
        "jurisdiction": m.get("jurisdiction") or "us",
        "office_type": m.get("office_type") or "senator",
    }


def run_sync(chambers: list[str] | None, apply: bool) -> dict:
    members = load_members(chambers=chambers, include_unconfigured=True)
    log.info("Loaded %d members from seeds (chambers=%s)", len(members), chambers or "all")

    if not apply:
        from collections import Counter
        # Group by (jurisdiction, chamber) since chamber alone is no longer
        # unique post-migration-012 (TX state senators and US senators both
        # have chamber='senate'). Use string fallback so None (executives)
        # sorts cleanly.
        by_scope = Counter(
            (m.get("jurisdiction") or "?", m.get("chamber") or "—")
            for m in members
        )
        log.info("Dry-run. Would UPSERT %d rows.", len(members))
        for (juris, chamber), n in sorted(by_scope.items()):
            log.info("  jurisdiction=%-4s chamber=%-12s rows=%d", juris, chamber, n)
        return {"loaded": len(members), "applied": 0}

    if not DB_URL:
        raise SystemExit("DATABASE_URL is not set; refusing to apply.")

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    inserted_or_updated = 0
    try:
        for m in members:
            params = member_to_params(m)
            cur.execute(UPSERT_SQL, params)
            inserted_or_updated += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    log.info("Applied %d UPSERTs.", inserted_or_updated)
    return {"loaded": len(members), "applied": inserted_or_updated}


def main():
    parser = argparse.ArgumentParser(description="Sync seed members into the senators table")
    parser.add_argument(
        "--chamber",
        action="append",
        help="Limit to one or more chambers (repeat flag). Default: all.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to the DB. Without this, prints a dry-run report.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    stats = run_sync(chambers=args.chamber, apply=args.apply)
    print(
        f"\n{'Applied' if args.apply else 'Dry-run'}: "
        f"loaded={stats['loaded']} applied={stats['applied']}"
    )


if __name__ == "__main__":
    main()
