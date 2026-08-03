"""
Collapse the duplicate-alert backlog left by the pre-dedup store_alert().

Until 2026-07-25, store_alert() did a plain INSERT on every call. The updater
runs 4x/day and re-derives the same anomalies each time, so one open condition
logged ~28 rows/week. Between 2026-04-18 and 2026-07-25 that produced 31,296
rows covering only ~545 distinct conditions.

Every consumer of the table (app/admin/page.tsx, app/api/admin/overview/route.ts,
`pipeline review alerts`) reads ORDER BY created_at DESC LIMIT 10-50. The
backlog therefore guaranteed that the admin dashboard showed nothing but
repeated "last release was X" info alerts, burying any genuine error or
critical alert.

store_alert() now touches the existing open row instead of inserting a
duplicate, which stops the growth. This script cleans up what already
accumulated.

NON-DESTRUCTIVE. No row is deleted. For each (alert_type, official_id, message)
group the newest unacknowledged row stays open and inherits first_seen plus an
occurrences count; the older duplicates are marked acknowledged so they drop
out of the dashboard queries while remaining fully readable in the table.

Re-runnable: a second run finds nothing left to collapse.

Usage:
    python -m pipeline.scripts.collapse_alert_backlog --dry-run
    python -m pipeline.scripts.collapse_alert_backlog
"""

import argparse
import json
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change without writing")
    args = ap.parse_args()

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # Survey first so the report is accurate whether or not we write.
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE NOT acknowledged) AS open_rows,
               COUNT(*) AS total_rows
        FROM alerts
    """)
    open_rows, total_rows = cur.fetchone()

    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT ON (alert_type, official_id, message) id
            FROM alerts WHERE NOT acknowledged
            ORDER BY alert_type, official_id, message, created_at DESC
        ) x
    """)
    distinct_conditions = cur.fetchone()[0]

    print(f"  alerts table:        {total_rows} rows total")
    print(f"  currently open:      {open_rows}")
    print(f"  distinct conditions: {distinct_conditions}")
    print(f"  would collapse:      {open_rows - distinct_conditions} duplicate rows")

    if args.dry_run:
        print("\n  dry run - nothing written")
        cur.close()
        conn.close()
        return

    # Fold each group's history into the row that stays open, so collapsing
    # the backlog does not throw away when the condition was first seen or how
    # many times it recurred.
    cur.execute("""
        WITH grouped AS (
            SELECT alert_type, official_id, message,
                   COUNT(*) AS occurrences,
                   MIN(created_at) AS first_seen,
                   (ARRAY_AGG(id ORDER BY created_at DESC))[1] AS keep_id
            FROM alerts
            WHERE NOT acknowledged
            GROUP BY alert_type, official_id, message
            HAVING COUNT(*) > 1
        )
        UPDATE alerts a
        SET details = COALESCE(a.details, '{}'::jsonb)
                      || jsonb_build_object(
                             'first_seen', to_char(g.first_seen, 'YYYY-MM-DD"T"HH24:MI:SSOF'),
                             'occurrences', g.occurrences)
        FROM grouped g
        WHERE a.id = g.keep_id
    """)
    kept = cur.rowcount

    # Everything older in each group is superseded by the row above. Mark it
    # acknowledged rather than deleting it: the dashboard queries filter on
    # acknowledged, so this clears the noise while preserving the audit trail.
    cur.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (
                       PARTITION BY alert_type, official_id, message
                       ORDER BY created_at DESC) AS rn
            FROM alerts
            WHERE NOT acknowledged
        )
        UPDATE alerts a
        SET acknowledged = TRUE,
            acknowledged_at = NOW(),
            details = COALESCE(a.details, '{}'::jsonb)
                      || jsonb_build_object('collapsed_as_duplicate', true)
        FROM ranked r
        WHERE a.id = r.id AND r.rn > 1
    """)
    collapsed = cur.rowcount

    conn.commit()
    cur.close()
    conn.close()

    print(f"\n  conditions annotated: {kept}")
    print(f"  duplicates collapsed: {collapsed}")
    print("  no rows deleted")


if __name__ == "__main__":
    main()
