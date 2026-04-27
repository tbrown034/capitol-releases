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


async def check_urls(
    urls: list[tuple[str, str, str]],  # (id, senator_id, source_url)
    max_concurrent: int = 10,
) -> list[dict]:
    """Check a batch of URLs for 404/410 responses.

    Uses GET (not HEAD) because HEAD is unreliable on many Senate sites.
    Returns list of detected deletions.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    deletions = []

    async def check_one(client, record_id, senator_id, url):
        async with semaphore:
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code in (404, 410):
                    deletions.append({
                        "id": record_id,
                        "senator_id": senator_id,
                        "source_url": url,
                        "status_code": resp.status_code,
                    })
                    log.info("DELETED: %s [%d] %s", senator_id, resp.status_code, url[:80])
                elif resp.status_code == 200:
                    # Still live -- update last_seen_live
                    pass  # handled in batch after
            except Exception as e:
                log.debug("Check failed for %s: %s", url[:60], type(e).__name__)
            await asyncio.sleep(0.2)  # politeness

    async with create_client(timeout=15.0) as client:
        tasks = [check_one(client, rid, sid, url) for rid, sid, url in urls]
        await asyncio.gather(*tasks)

    return deletions


def get_urls_to_check(conn, senator_id: str = None, batch_size: int = 500) -> list[tuple]:
    """Get URLs to check, prioritizing those not recently verified."""
    cur = conn.cursor()
    # Allowed source domains: any first-party .gov site we collect from.
    # Keep this in sync with classifier.is_external_content() and any new
    # chamber additions (house.gov when we expand beyond Senate).
    query = """
        SELECT id::text, senator_id, source_url
        FROM press_releases
        WHERE deleted_at IS NULL
        AND (
          source_url LIKE '%%senate.gov%%'
          OR source_url LIKE '%%whitehouse.gov%%'
          OR source_url LIKE '%%house.gov%%'
        )
    """
    params = []
    if senator_id:
        query += " AND senator_id = %s"
        params.append(senator_id)

    # Prioritize records never checked or least recently checked
    query += """
        ORDER BY
            CASE WHEN last_seen_live IS NULL THEN 0 ELSE 1 END,
            last_seen_live ASC NULLS FIRST
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
    senator_id: str = None,
    batch_size: int = 500,
    dry_run: bool = False,
):
    conn = psycopg2.connect(DB_URL)

    # Add deleted_at and last_seen_live columns if they don't exist
    cur = conn.cursor()
    cur.execute("ALTER TABLE press_releases ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
    cur.execute("ALTER TABLE press_releases ADD COLUMN IF NOT EXISTS last_seen_live TIMESTAMPTZ")
    conn.commit()
    cur.close()

    urls = get_urls_to_check(conn, senator_id, batch_size)
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
            print(f"  [DRY DELETE] {d['senator_id']}: {d['source_url'][:80]}")
    else:
        for d in deletions:
            mark_deleted(conn, d["id"])
            alert = Alert(
                alert_type="deletion_detected",
                severity="info",
                message=f"Release deleted: {d['source_url'][:80]}",
                senator_id=d["senator_id"],
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
        senator_id=args.senator,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    ))

    print(f"\nSummary: {stats['checked']} checked, {stats['deleted']} deleted, {stats['still_live']} live")


if __name__ == "__main__":
    main()
