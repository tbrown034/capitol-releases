"""
Capitol Releases -- Review Surface

Inspect low-confidence dates, recent alerts, pipeline health,
and flagged records. Not fancy -- just visible.

Usage:
    python -m pipeline.commands.review alerts        # recent alerts
    python -m pipeline.commands.review health        # latest health check results
    python -m pipeline.commands.review stale         # senators with old data
    python -m pipeline.commands.review quality       # data quality overview
    python -m pipeline.commands.review runs          # recent scrape runs
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

# Load .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.environ["DATABASE_URL"]


def show_alerts():
    """Show recent unacknowledged alerts."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT created_at, alert_type, severity, senator_id, message
        FROM alerts
        WHERE acknowledged = FALSE
        ORDER BY created_at DESC
        LIMIT 50
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        print("\nNo unacknowledged alerts.")
        return

    print(f"\n{'='*70}")
    print(f"  UNACKNOWLEDGED ALERTS ({len(rows)})")
    print(f"{'='*70}")
    for ts, atype, severity, sid, msg in rows:
        ts_str = ts.strftime("%Y-%m-%d %H:%M") if ts else "?"
        sid_str = f" [{sid}]" if sid else ""
        sev_icon = {"critical": "!!!", "error": "!!", "warning": "!", "info": " "}.get(severity, " ")
        print(f"  {sev_icon} {ts_str}  {atype:20s}{sid_str}")
        print(f"    {msg}")
    print()


def show_health():
    """Show latest health check results per senator."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (senator_id)
            senator_id, checked_at, passed, url_status, items_found,
            page_load_ms, error_message
        FROM health_checks
        ORDER BY senator_id, checked_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        print("\nNo health check data. Run: python -m pipeline health")
        return

    passed = [r for r in rows if r[2]]
    failed = [r for r in rows if not r[2]]

    print(f"\n{'='*70}")
    print(f"  HEALTH CHECK STATUS")
    print(f"  Passed: {len(passed)}  Failed: {len(failed)}")
    print(f"{'='*70}")

    if failed:
        print(f"\n  --- FAILING ---")
        for sid, ts, ok, status, items, ms, err in sorted(failed, key=lambda x: x[0]):
            print(f"  {sid:30s} HTTP {status or '?':>3}  {items or 0:>3} items  {err or ''}")
    print()


def show_stale():
    """Show senators with the oldest data."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.full_name, s.collection_method,
               MAX(pr.published_at) as last_release,
               COUNT(*) as total
        FROM senators s
        LEFT JOIN press_releases pr ON s.id = pr.senator_id
        GROUP BY s.id, s.full_name, s.collection_method
        ORDER BY MAX(pr.published_at) ASC NULLS FIRST
        LIMIT 20
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    print(f"\n{'='*70}")
    print(f"  STALEST SENATORS (oldest last release)")
    print(f"{'='*70}")
    for sid, name, method, last, total in rows:
        last_str = last.strftime("%Y-%m-%d") if last else "never"
        print(f"  {name:30s} {method or '?':10s} last: {last_str:12s} total: {total:>5}")
    print()


def show_quality():
    """Show data quality overview."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM press_releases")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM press_releases WHERE published_at IS NOT NULL")
    dated = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM press_releases WHERE body_text IS NOT NULL AND length(body_text) > 100")
    with_body = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM press_releases WHERE deleted_at IS NOT NULL")
    deleted = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM press_releases WHERE date_source IS NOT NULL")
    with_provenance = cur.fetchone()[0]

    cur.execute("""
        SELECT content_type, COUNT(*)
        FROM press_releases
        GROUP BY content_type
        ORDER BY COUNT(*) DESC
    """)
    types = cur.fetchall()

    cur.execute("""
        SELECT date_source, COUNT(*)
        FROM press_releases
        WHERE date_source IS NOT NULL
        GROUP BY date_source
        ORDER BY COUNT(*) DESC
    """)
    sources = cur.fetchall()

    cur.close()
    conn.close()

    print(f"\n{'='*50}")
    print(f"  DATA QUALITY OVERVIEW")
    print(f"{'='*50}")
    print(f"  Total records:       {total:>8,}")
    print(f"  With dates:          {dated:>8,} ({dated/total*100:.0f}%)")
    print(f"  With body text:      {with_body:>8,} ({with_body/total*100:.0f}%)")
    print(f"  With date provenance:{with_provenance:>8,}")
    print(f"  Deleted (tombstones):{deleted:>8,}")

    print(f"\n  Content types:")
    for ctype, cnt in types:
        print(f"    {ctype or 'unset':20s} {cnt:>6,}")

    if sources:
        print(f"\n  Date sources:")
        for src, cnt in sources:
            print(f"    {src:20s} {cnt:>6,}")
    print(f"{'='*50}\n")


def show_runs():
    """Show recent scrape runs."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, run_type, started_at, finished_at, stats
        FROM scrape_runs
        ORDER BY started_at DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    print(f"\n{'='*70}")
    print(f"  RECENT SCRAPE RUNS")
    print(f"{'='*70}")
    for rid, rtype, started, finished, stats in rows:
        duration = ""
        if started and finished:
            secs = (finished - started).total_seconds()
            duration = f"{secs:.0f}s"
        stats_data = stats if isinstance(stats, dict) else json.loads(stats) if stats else {}
        inserted = stats_data.get("total_inserted", "?")
        errors = stats_data.get("total_errors", "?")
        print(f"  {rid:30s} {rtype:8s} {started.strftime('%Y-%m-%d %H:%M') if started else '?':>16} {duration:>6} +{inserted} err={errors}")
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    commands = {
        "alerts": show_alerts,
        "health": show_health,
        "stale": show_stale,
        "quality": show_quality,
        "runs": show_runs,
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown review command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
