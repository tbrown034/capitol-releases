"""
Capitol Releases -- Daily Updater (Script 3)

Fetches new press releases from all senators since the last run.
Uses the collector registry to route each senator to their canonical
collection method (RSS, httpx, or Playwright).

Usage:
    python -m pipeline.commands.update
    python -m pipeline.commands.update --senators warren-elizabeth fetterman-john
    python -m pipeline.commands.update --dry-run
"""

import asyncio
import json
import logging
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

import psycopg2

from pipeline.collectors.base import ReleaseRecord
from pipeline.collectors.registry import CollectorRegistry
from pipeline.lib.identity import normalize_url

# Load .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.environ["DATABASE_URL"]

log = logging.getLogger("capitol.update")


def get_last_run_time(conn) -> datetime | None:
    """Get the timestamp of the last successful update run."""
    cur = conn.cursor()
    cur.execute("""
        SELECT finished_at FROM scrape_runs
        WHERE run_type = 'daily' AND finished_at IS NOT NULL
        ORDER BY finished_at DESC LIMIT 1
    """)
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def get_existing_urls(conn, senator_id: str) -> set[str]:
    """Get all known source_urls for a senator (for dedup)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT source_url FROM press_releases WHERE senator_id = %s",
        (senator_id,),
    )
    urls = {normalize_url(row[0]) for row in cur.fetchall()}
    cur.close()
    return urls


def upsert_release(conn, release: ReleaseRecord) -> tuple[bool, bool]:
    """Upsert a release with content versioning.

    Returns (is_new, was_updated):
      - is_new=True   when source_url was not in the DB
      - was_updated=True when source_url existed but content_hash changed; in
        that case the prior body is moved into content_versions before the
        main row is updated.

    The archival mission requires capturing edits, not just first-publish: a
    senator silently rewriting a release after it goes live should leave a
    trail. Pure ON CONFLICT DO NOTHING (the prior behavior) lost those edits.
    """
    canonical = normalize_url(release.source_url)
    run_id = f"daily-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, content_hash, body_text FROM press_releases WHERE source_url = %s",
            (canonical,),
        )
        existing = cur.fetchone()

        if existing is None:
            cur.execute(
                """
                INSERT INTO press_releases
                    (senator_id, title, published_at, body_text, source_url,
                     raw_html, content_type, date_source, date_confidence,
                     content_hash, scrape_run, scraped_at, last_seen_live)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (source_url) DO NOTHING
                """,
                (
                    release.senator_id,
                    release.title,
                    release.published_at,
                    release.body_text or None,
                    canonical,
                    release.raw_html or None,
                    release.content_type,
                    release.date_source or None,
                    release.date_confidence or None,
                    release.content_hash or None,
                    run_id,
                ),
            )
            conn.commit()
            return (cur.rowcount > 0, False)

        existing_id, existing_hash, existing_body = existing
        new_hash = release.content_hash or None

        # Always bump last_seen_live so the deletion detector knows the URL is
        # still resolving from the source.
        cur.execute(
            "UPDATE press_releases SET last_seen_live = NOW() WHERE id = %s",
            (existing_id,),
        )

        # If we have hashes on both sides and they differ, archive the old
        # version then update the main row. If either hash is missing we
        # cannot reliably detect an edit, so we treat this as a no-op.
        if new_hash and existing_hash and new_hash != existing_hash:
            cur.execute(
                """
                INSERT INTO content_versions
                    (press_release_id, body_text, content_hash, captured_at)
                VALUES (%s, %s, %s, NOW())
                """,
                (existing_id, existing_body, existing_hash),
            )
            cur.execute(
                """
                UPDATE press_releases
                SET title = %s,
                    body_text = %s,
                    content_hash = %s,
                    raw_html = COALESCE(%s, raw_html),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    release.title,
                    release.body_text or None,
                    new_hash,
                    release.raw_html or None,
                    existing_id,
                ),
            )
            conn.commit()
            return (False, True)

        conn.commit()
        return (False, False)
    except Exception as e:
        conn.rollback()
        log.error("Upsert failed for %s: %s", release.source_url, e)
        return (False, False)
    finally:
        cur.close()


def record_run(conn, run_id: str, stats: dict, started_at: datetime):
    """Record this scrape run in the scrape_runs table."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO scrape_runs (id, run_type, started_at, finished_at, stats)
        VALUES (%s, 'daily', %s, NOW(), %s)
        ON CONFLICT (id) DO UPDATE SET finished_at = NOW(), stats = %s
    """, (run_id, started_at, json.dumps(stats), json.dumps(stats)))
    conn.commit()
    cur.close()


async def run_update(
    senators: list[dict],
    since: datetime | None = None,
    dry_run: bool = False,
    max_concurrent: int = 6,
):
    """Run the daily update for all senators."""
    started_at = datetime.now(timezone.utc)
    run_id = f"daily-{started_at.strftime('%Y-%m-%d-%H%M')}"

    conn = psycopg2.connect(DB_URL) if not dry_run else None

    # Determine cutoff: last run time or 7 days ago as default
    if not since and conn:
        since = get_last_run_time(conn)
    if not since:
        since = datetime.now(timezone.utc) - timedelta(days=7)

    log.info("Update starting. Since: %s. Senators: %d", since.isoformat(), len(senators))

    registry = CollectorRegistry()
    semaphore = asyncio.Semaphore(max_concurrent)

    total_inserted = 0
    total_updated = 0
    total_skipped = 0
    total_errors = 0
    senator_results = []

    async def process_senator(senator):
        nonlocal total_inserted, total_updated, total_skipped, total_errors

        async with semaphore:
            sid = senator["senator_id"]
            expect_empty = bool(senator.get("expect_empty"))
            collector = registry.get_collector(senator)

            try:
                result = await collector.collect(senator, since=since, max_pages=1)
            except Exception as e:
                log.error("Collector crashed for %s: %s: %s", sid, type(e).__name__, e)
                if not expect_empty:
                    total_errors += 1
                senator_results.append({"senator_id": sid, "error": str(e)})
                return

            if result.errors:
                if expect_empty and not result.releases:
                    for err in result.errors:
                        log.info("Expected-empty senator %s: %s", sid, err)
                else:
                    for err in result.errors:
                        log.warning("Collector error for %s: %s", sid, err)
                    total_errors += len(result.errors)

            inserted = 0
            updated = 0
            skipped = 0
            for release in result.releases:
                if dry_run:
                    date_str = release.published_at.strftime("%Y-%m-%d") if release.published_at else "no date"
                    print(f"  [DRY] {sid}: {date_str} | {release.title[:70]}")
                    inserted += 1
                    continue

                is_new, was_updated = upsert_release(conn, release)
                if is_new:
                    inserted += 1
                    date_str = release.published_at.strftime("%Y-%m-%d") if release.published_at else "no date"
                    log.info("  + %s: %s | %s", sid, date_str, release.title[:70])
                elif was_updated:
                    updated += 1
                    log.info("  ~ %s: %s | %s (content changed)", sid, release.published_at.strftime("%Y-%m-%d") if release.published_at else "no date", release.title[:70])
                else:
                    skipped += 1

            total_inserted += inserted
            total_updated += updated
            total_skipped += skipped

            senator_results.append({
                "senator_id": sid,
                "method": result.method,
                "collected": len(result.releases),
                "inserted": inserted,
                "updated": updated,
                "skipped": skipped,
                "duration_s": round(result.duration_seconds, 1),
                "errors": result.errors,
            })

            if inserted > 0 or updated > 0:
                log.info("%s: +%d new, ~%d updated, %d skipped (via %s)", sid, inserted, updated, skipped, result.method)

    # Run all senators concurrently
    tasks = [process_senator(s) for s in senators]
    await asyncio.gather(*tasks)

    # Record the run
    stats = {
        "total_inserted": total_inserted,
        "total_updated": total_updated,
        "total_skipped": total_skipped,
        "total_errors": total_errors,
        "senators_processed": len(senator_results),
        "senators_with_new": sum(1 for r in senator_results if r.get("inserted", 0) > 0),
        "senators_with_updates": sum(1 for r in senator_results if r.get("updated", 0) > 0),
    }

    if conn and not dry_run:
        record_run(conn, run_id, stats, started_at)

        # Run anomaly detection after update
        try:
            from pipeline.lib.alerts import check_anomalies, store_alert, send_email_alerts
            anomalies = check_anomalies(conn)
            if anomalies:
                log.info("Anomaly detection found %d issue(s)", len(anomalies))
                for alert in anomalies:
                    store_alert(conn, alert)
                    log.warning("ALERT [%s] %s: %s", alert.severity, alert.alert_type, alert.message)
                send_email_alerts(anomalies)
            stats["anomalies"] = len(anomalies)
        except Exception as e:
            log.error("Anomaly detection failed: %s", e)

        conn.close()

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    log.info(
        "Update complete in %.1fs. +%d new, ~%d updated, %d skipped, %d errors across %d senators",
        elapsed, total_inserted, total_updated, total_skipped, total_errors, len(senator_results),
    )

    return stats


def main():
    parser = argparse.ArgumentParser(description="Capitol Releases daily updater")
    parser.add_argument("--senators", nargs="*", help="Only update specific senators")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be inserted")
    parser.add_argument("--since", help="Override cutoff date (ISO format)")
    parser.add_argument("--max-concurrent", type=int, default=6)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load members across all chambers (senate + executive, future: house)
    from pipeline.lib.seeds import load_members
    senators = load_members()

    # Filter if specific senators requested
    if args.senators:
        senators = [s for s in senators if s["senator_id"] in args.senators]
        if not senators:
            print(f"No senators matched: {args.senators}")
            sys.exit(1)

    since = None
    if args.since:
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)

    stats = asyncio.run(run_update(
        senators=senators,
        since=since,
        dry_run=args.dry_run,
        max_concurrent=args.max_concurrent,
    ))

    print(
        f"\nSummary: +{stats['total_inserted']} new, "
        f"~{stats.get('total_updated', 0)} updated, "
        f"{stats['total_skipped']} skipped, "
        f"{stats['total_errors']} errors"
    )


if __name__ == "__main__":
    main()
