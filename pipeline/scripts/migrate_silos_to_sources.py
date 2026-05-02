"""
Migrate House silos from pipeline/recon/house_full_recon.json into
official_sources.

Step 3 of the official_sources migration plan
(docs/official-sources-migration-plan-2026-05-02.md). Once this lands,
pipeline/scripts/backfill_house_silos.py can be rewritten to read silos
from the DB instead of recon JSON.

What this script does
---------------------
- Reads pipeline/recon/house_full_recon.json and walks every result's
  channels[] array.
- Filters to the channels we want to surface as official_sources rows:
    * is_listing == True
    * not rejected
    * status_code == 200
    * content_type in {op_ed, blog, newsletter, floor_statement,
                       statement, letter}
  Press releases are deliberately excluded -- those are the primary
  source on the officials row and are backfilled by migration 017.
- UPSERTs into official_sources with:
    source_type = 'html_listing'
    content_scope = channel content_type
    collection_method = 'httpx'
    scrape_config = {selectors, pagination} from the recon
    notes = 'silo backfill from house_full_recon.json'
- Idempotent via ON CONFLICT (official_id, url) DO NOTHING.

Connection / argparse shape mirrors pipeline/commands/sync_members.py:
default is dry-run, --apply actually writes.

Usage
-----
    python -m pipeline.scripts.migrate_silos_to_sources              # dry-run
    python -m pipeline.scripts.migrate_silos_to_sources --apply      # write
    python -m pipeline.scripts.migrate_silos_to_sources --member palmer-gary --dry-run
    python -m pipeline.scripts.migrate_silos_to_sources --content-type op_ed --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
RECON_FILE = ROOT / "pipeline" / "recon" / "house_full_recon.json"

log = logging.getLogger("capitol.migrate_silos_to_sources")
DB_URL = os.environ.get("DATABASE_URL")

# content_types we promote to official_sources rows. press_release is
# excluded -- it's already represented as the primary source on the
# officials row (and migration 017 backfills it).
SILO_CONTENT_TYPES: set[str] = {
    "op_ed",
    "blog",
    "newsletter",
    "floor_statement",
    "statement",
    "letter",
}


UPSERT_SQL = """
    INSERT INTO official_sources (
        official_id, source_type, content_scope, url, collection_method,
        scrape_config, active, notes
    ) VALUES (
        %(official_id)s, %(source_type)s, %(content_scope)s, %(url)s,
        %(collection_method)s, %(scrape_config)s::jsonb, TRUE,
        %(notes)s
    )
    ON CONFLICT ON CONSTRAINT uq_official_source_url DO NOTHING
"""


def load_silos() -> list[dict]:
    """Read house_full_recon.json and yield per-silo dicts ready for UPSERT."""
    if not RECON_FILE.exists():
        raise SystemExit(
            f"{RECON_FILE} missing. Run pipeline/recon/house_full_recon.py first."
        )
    recon = json.loads(RECON_FILE.read_text())
    out: list[dict] = []
    for r in recon.get("results", []):
        member_id = r.get("member_id")
        if not member_id:
            continue
        for c in r.get("channels", []):
            if not c.get("is_listing"):
                continue
            if c.get("rejected"):
                continue
            if c.get("status_code") != 200:
                continue
            ct = c.get("content_type")
            if ct not in SILO_CONTENT_TYPES:
                continue
            url = c.get("url")
            if not url:
                continue
            cfg: dict = {}
            if c.get("selectors"):
                cfg["selectors"] = c["selectors"]
            if c.get("pagination"):
                cfg["pagination"] = c["pagination"]
            out.append(
                {
                    "official_id": member_id,
                    "source_type": "html_listing",
                    "content_scope": ct,
                    "url": url,
                    "collection_method": "httpx",
                    "scrape_config": json.dumps(cfg) if cfg else None,
                    "notes": "silo backfill from house_full_recon.json",
                }
            )
    return out


def run_migrate(
    member: str | None,
    content_type: str | None,
    apply: bool,
) -> dict:
    silos = load_silos()
    if member:
        silos = [s for s in silos if s["official_id"] == member]
    if content_type:
        silos = [s for s in silos if s["content_scope"] == content_type]

    log.info("Loaded %d silo rows from %s", len(silos), RECON_FILE.name)

    by_ct = Counter(s["content_scope"] for s in silos)
    by_member = Counter(s["official_id"] for s in silos)
    log.info("Distinct members: %d", len(by_member))
    for ct, n in sorted(by_ct.items(), key=lambda kv: (-kv[1], kv[0])):
        log.info("  %-18s %d", ct, n)

    if not apply:
        log.info("Dry-run. Would UPSERT %d official_sources rows.", len(silos))
        # Print a small preview for sanity.
        for s in silos[:5]:
            log.info("  preview: %s | %s | %s", s["official_id"], s["content_scope"], s["url"])
        return {"loaded": len(silos), "applied": 0}

    if not DB_URL:
        raise SystemExit("DATABASE_URL is not set; refusing to apply.")

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    inserted = 0
    skipped_existing = 0
    try:
        for s in silos:
            cur.execute(UPSERT_SQL, s)
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped_existing += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    log.info(
        "Applied. inserted=%d skipped_existing=%d total=%d",
        inserted, skipped_existing, len(silos),
    )
    return {
        "loaded": len(silos),
        "applied": inserted,
        "skipped_existing": skipped_existing,
    }


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Migrate House silos from house_full_recon.json into "
            "official_sources. Idempotent."
        )
    )
    ap.add_argument(
        "--member",
        help="Limit to a single official_id (e.g. palmer-gary).",
    )
    ap.add_argument(
        "--content-type",
        choices=sorted(SILO_CONTENT_TYPES),
        help="Limit to one content_type.",
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to the DB. Without this, prints a dry-run report.",
    )
    g.add_argument(
        "--dry-run",
        action="store_true",
        help="Default behaviour; included for explicit invocation.",
    )
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    apply = bool(args.apply) and not args.dry_run
    stats = run_migrate(
        member=args.member,
        content_type=args.content_type,
        apply=apply,
    )
    print(
        f"\n{'Applied' if apply else 'Dry-run'}: "
        f"loaded={stats['loaded']} applied={stats['applied']}"
        + (
            f" skipped_existing={stats['skipped_existing']}"
            if "skipped_existing" in stats
            else ""
        )
    )


if __name__ == "__main__":
    main()
