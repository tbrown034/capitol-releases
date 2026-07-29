"""
Capitol Releases -- Deletion Detection

Periodically checks if previously-scraped releases are still live.
If a senator deletes a press release, we detect it and flag it as
a tombstone -- never hard-delete from our archive.

This is one of the most journalistically valuable features:
"Senator X deleted 12 press releases about Y after Z happened."

Usage:
    python -m pipeline.commands.detect_deletions
    python -m pipeline.commands.detect_deletions --senator warren-elizabeth
    python -m pipeline.commands.detect_deletions --batch-size 200
    python -m pipeline.commands.detect_deletions --dry-run
"""

import asyncio
import json
import logging
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from pipeline.lib.http import create_client
from pipeline.lib.alerts import Alert, store_alert

# Load .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.environ["DATABASE_URL"]

log = logging.getLogger("capitol.deletions")


# A first 404/410 hit is treated as a candidate, not a tombstone. The detector
# requires CONFIRMATION_RUNS independent re-checks before tombstoning. The
# 2026-04-19 incident produced 1,286 false-positive tombstones because a single
# transient 404 (likely Akamai/CDN behavior) was treated as deletion -- 1,283
# of 1,286 returned 200 on browser-UA reverification a week later.
CONFIRMATION_RUNS = 3
CONFIRMATION_SPACING_S = 60  # seconds between confirmation re-checks


async def check_urls(
    urls: list[tuple[str, str, str]],  # (id, official_id, source_url)
    max_concurrent: int = 10,
) -> list[dict]:
    """Check a batch of URLs for 404/410 responses.

    Any candidate 404/410 is re-checked CONFIRMATION_RUNS times with
    CONFIRMATION_SPACING_S seconds between checks before being treated as a
    real deletion. Single hits are too noisy for tombstoning.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    deletions: list[dict] = []

    async def confirm(client, url) -> int | None:
        # Returns the final status code if every confirmation pass agrees on
        # 404/410; None otherwise.
        first = None
        for i in range(CONFIRMATION_RUNS):
            try:
                resp = await client.get(url, follow_redirects=True)
                code = resp.status_code
            except Exception:
                return None
            if code not in (404, 410):
                return None
            if first is None:
                first = code
            elif code != first:
                return None
            if i < CONFIRMATION_RUNS - 1:
                await asyncio.sleep(CONFIRMATION_SPACING_S)
        return first

    async def check_one(client, record_id, official_id, url):
        async with semaphore:
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code in (404, 410):
                    confirmed = await confirm(client, url)
                    if confirmed is not None:
                        deletions.append({
                            "id": record_id,
                            "official_id": official_id,
                            "source_url": url,
                            "status_code": confirmed,
                        })
                        log.info(
                            "DELETED (confirmed %dx): %s [%d] %s",
                            CONFIRMATION_RUNS, official_id, confirmed, url[:80],
                        )
                    else:
                        log.info(
                            "DELETION CANDIDATE NOT CONFIRMED: %s %s",
                            official_id, url[:80],
                        )
            except Exception as e:
                log.debug("Check failed for %s: %s", url[:60], type(e).__name__)
            await asyncio.sleep(0.2)  # politeness

    async with create_client(timeout=15.0) as client:
        tasks = [check_one(client, rid, sid, url) for rid, sid, url in urls]
        await asyncio.gather(*tasks)

    return deletions


def get_urls_to_check(conn, official_id: str = None, batch_size: int = 500) -> list[tuple]:
    """Get URLs to check, prioritizing those not recently verified."""
    cur = conn.cursor()
    # Allowed source hosts are DERIVED from the sources we actually collect,
    # not listed here. The previous hardcoded senate.gov / whitehouse.gov /
    # house.gov filter silently excluded every state record from deletion
    # detection: as of 2026-07-28 that was 8,121 items across seven
    # jurisdictions that had never once been checked for takedown, despite
    # archival permanence being a core guarantee. Colorado made the flaw
    # obvious -- its caucus sources are on .com and .co domains and could
    # never have matched a .gov allowlist.
    #
    # Deriving from officials.press_release_url keeps the guard the list was
    # there for (third-party URLs that leaked into the corpus are still
    # skipped, because no configured source publishes on their host) while
    # covering any jurisdiction the moment it is seeded.
    query = """
        WITH allowed_hosts AS (
            SELECT DISTINCT lower(regexp_replace(
                       press_release_url, '^https?://(?:www\\.)?([^/?#]+).*$', '\\1'
                   )) AS host
            FROM officials
            WHERE press_release_url IS NOT NULL
              AND collection_method IS NOT NULL
        )
        SELECT i.id::text, i.official_id, i.source_url
        FROM official_site_items i
        WHERE i.deleted_at IS NULL
          AND (
            -- Derived hosts cover every seeded jurisdiction, including the
            -- non-.gov caucus domains.
            lower(regexp_replace(
              i.source_url, '^https?://(?:www\\.)?([^/?#]+).*$', '\\1'
            )) IN (SELECT host FROM allowed_hosts)
            -- The original federal domains are kept as a floor. Deriving
            -- hosts ALONE dropped 458 federal items whose URLs sit on a
            -- different subdomain than the seeded listing page -- silo and
            -- wp-json backfills legitimately do this -- and quietly
            -- narrowing existing coverage while widening it elsewhere is
            -- the kind of trade that goes unnoticed for months.
            OR i.source_url LIKE '%%.senate.gov/%%'
            OR i.source_url LIKE '%%.house.gov/%%'
            OR i.source_url LIKE '%%whitehouse.gov/%%'
          )
    """
    params = []
    if official_id:
        query += " AND i.official_id = %s"
        params.append(official_id)

    # Prioritize records never checked or least recently checked
    query += """
        ORDER BY
            CASE WHEN i.last_seen_live IS NULL THEN 0 ELSE 1 END,
            i.last_seen_live ASC NULLS FIRST
        LIMIT %s
    """
    params.append(batch_size)

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def mark_deleted(conn, record_id: str):
    """Mark a press release as deleted (tombstone, never hard-delete)."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE press_releases
        SET deleted_at = NOW(), updated_at = NOW()
        WHERE id = %s::uuid
    """, (record_id,))
    conn.commit()
    cur.close()


def mark_seen_live(conn, record_ids: list[str]):
    """Update last_seen_live for records confirmed still accessible."""
    if not record_ids:
        return
    cur = conn.cursor()
    cur.execute("""
        UPDATE press_releases
        SET last_seen_live = NOW()
        WHERE id = ANY(%s::uuid[])
    """, (record_ids,))
    conn.commit()
    cur.close()


async def run_deletion_check(
    official_id: str = None,
    batch_size: int = 500,
    dry_run: bool = False,
):
    conn = psycopg2.connect(DB_URL)

    cur = conn.cursor()
    cur.execute("ALTER TABLE official_site_items ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
    cur.execute("ALTER TABLE official_site_items ADD COLUMN IF NOT EXISTS last_seen_live TIMESTAMPTZ")
    conn.commit()
    cur.close()

    urls = get_urls_to_check(conn, official_id, batch_size)
    log.info("Checking %d URLs for deletions", len(urls))

    if not urls:
        log.info("No URLs to check")
        conn.close()
        return {"checked": 0, "deleted": 0}

    deletions = await check_urls(urls)
    checked_ids = [str(rid) for rid, _, _ in urls]
    deleted_ids = {d["id"] for d in deletions}
    live_ids = [rid for rid in checked_ids if rid not in deleted_ids]

    if dry_run:
        for d in deletions:
            print(f"  [DRY DELETE] {d['official_id']}: {d['source_url'][:80]}")
    else:
        for d in deletions:
            mark_deleted(conn, d["id"])
            alert = Alert(
                alert_type="deletion_detected",
                severity="info",
                message=f"Release deleted: {d['source_url'][:80]}",
                official_id=d["official_id"],
                details={"source_url": d["source_url"], "status_code": d["status_code"]},
            )
            store_alert(conn, alert)

        mark_seen_live(conn, live_ids)

    stats = {
        "checked": len(urls),
        "deleted": len(deletions),
        "still_live": len(live_ids),
    }
    log.info(
        "Deletion check complete: %d checked, %d deleted, %d live",
        stats["checked"], stats["deleted"], stats["still_live"],
    )

    conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Capitol Releases deletion detection")
    parser.add_argument("--senator", help="Only check specific senator")
    parser.add_argument("--batch-size", type=int, default=500, help="URLs to check per run")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    stats = asyncio.run(run_deletion_check(
        official_id=args.senator,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    ))

    print(f"\nSummary: {stats['checked']} checked, {stats['deleted']} deleted, {stats['still_live']} live")


if __name__ == "__main__":
    main()
