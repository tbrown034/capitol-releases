"""
Capitol Releases -- Health Check (Pre-Scrape Canary)

For each senator, verifies that their collection method is working:
- RSS senators: feed returns 200, contains items, dates parseable
- httpx senators: URL returns 200, selectors find items
- Reports per-senator pass/fail with details

Run before every update cycle to catch breakage early.

Usage:
    python -m pipeline.commands.health_check
    python -m pipeline.commands.health_check --senators warren-elizabeth
    python -m pipeline.commands.health_check --method rss
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

from pipeline.collectors.registry import CollectorRegistry
from pipeline.collectors.base import HealthCheckResult

# Load .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.environ["DATABASE_URL"]

log = logging.getLogger("capitol.health")


def store_health_check(conn, result: HealthCheckResult):
    """Store a health check result in the database."""
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO health_checks
                (senator_id, checked_at, url_status, selector_ok, items_found,
                 date_parseable, page_load_ms, error_message, passed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            result.senator_id,
            result.checked_at,
            result.url_status,
            result.selector_ok,
            result.items_found,
            result.date_parseable,
            result.page_load_ms,
            result.error_message or None,
            result.passed,
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error("Failed to store health check for %s: %s", result.senator_id, e)
    finally:
        cur.close()


async def run_health_checks(
    senators: list[dict],
    store_results: bool = True,
    max_concurrent: int = 8,
) -> list[HealthCheckResult]:
    """Run health checks for all senators."""
    started_at = datetime.now(timezone.utc)
    registry = CollectorRegistry()
    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[HealthCheckResult] = []

    conn = None
    if store_results:
        try:
            conn = psycopg2.connect(DB_URL)
            # Check if health_checks table exists
            cur = conn.cursor()
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'health_checks'
                )
            """)
            table_exists = cur.fetchone()[0]
            cur.close()
            if not table_exists:
                log.warning("health_checks table doesn't exist yet, skipping DB storage")
                conn.close()
                conn = None
        except Exception as e:
            log.warning("Could not connect to DB for health check storage: %s", e)
            conn = None

    async def check_one(senator):
        async with semaphore:
            collector = registry.get_collector(senator)
            try:
                result = await collector.health_check(senator)
            except Exception as e:
                result = HealthCheckResult(
                    senator_id=senator["senator_id"],
                    error_message=f"{type(e).__name__}: {e}",
                )
            results.append(result)

            if conn:
                store_health_check(conn, result)

            await asyncio.sleep(0.3)  # politeness

    tasks = [check_one(s) for s in senators]
    await asyncio.gather(*tasks)

    if conn:
        conn.close()

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    # Print results table
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]

    print(f"\n{'='*70}")
    print(f"HEALTH CHECK RESULTS  ({elapsed:.1f}s)")
    print(f"{'='*70}")
    print(f"  Passed: {len(passed)}/{len(results)}")
    print(f"  Failed: {len(failed)}/{len(results)}")

    if failed:
        print(f"\n--- FAILED ({len(failed)}) ---")
        for r in sorted(failed, key=lambda x: x.senator_id):
            status = f"HTTP {r.url_status}" if r.url_status else "no response"
            items = f"{r.items_found} items" if r.items_found else "0 items"
            err = f" | {r.error_message}" if r.error_message else ""
            print(f"  {r.senator_id:30s} {status:12s} {items:10s}{err}")

    if passed:
        print(f"\n--- PASSED ({len(passed)}) ---")
        for r in sorted(passed, key=lambda x: x.senator_id):
            print(f"  {r.senator_id:30s} HTTP {r.url_status}  {r.items_found:3d} items  {r.page_load_ms:4d}ms")

    print(f"\n{'='*70}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Capitol Releases health check")
    parser.add_argument("--senators", nargs="*", help="Only check specific senators")
    parser.add_argument("--method", choices=["rss", "httpx", "playwright"], help="Only check senators using this method")
    parser.add_argument("--no-store", action="store_true", help="Don't store results in DB")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load senators
    seed_path = Path(__file__).resolve().parent.parent / "seeds" / "senate.json"
    data = json.loads(seed_path.read_text())
    senators = data["members"]

    # Filter
    if args.senators:
        senators = [s for s in senators if s["senator_id"] in args.senators]
    if args.method:
        senators = [s for s in senators if s.get("collection_method") == args.method]

    if not senators:
        print("No senators matched filters")
        sys.exit(1)

    asyncio.run(run_health_checks(
        senators=senators,
        store_results=not args.no_store,
    ))


if __name__ == "__main__":
    main()
