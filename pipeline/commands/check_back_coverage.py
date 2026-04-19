"""
Capitol Releases -- Back-Coverage Health Check (Script 8)

Detects senators whose earliest archived record is meaningfully later
than their expected coverage start -- a signal the collector is only
reading recent pages and silently missing older releases.

Example: Heinrich (NM) has been in office since 2013 and publishes
regularly, but our earliest record is 2025-12-31. Everything before
that is missing because the HTML scraper capped at the first N
paginated pages. Previous coverage tests counted aggregate records
and missed this -- Heinrich had 107 records, which looked "fine" in
bulk, but was truncated in time.

This check computes a per-senator gap between expected coverage start
(default 2025-01-01) and actual earliest record, flags anything over
the threshold, and reports collector metadata so you can spot
patterns (JS-heavy, specific method, etc.).

Usage:
    python -m pipeline back-coverage                 # table of flagged senators
    python -m pipeline back-coverage --all           # every senator
    python -m pipeline back-coverage --threshold 30  # flag > 30-day gaps (default 60)
    python -m pipeline back-coverage --json          # machine-readable
"""
import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg2

DEFAULT_COVERAGE_START = date(2025, 1, 1)

# Current holders who took office after the window opens. For these,
# the expected earliest record is their in-office date, not 2025-01-01.
# Keep small and specific -- anything else falls back to DEFAULT_COVERAGE_START.
EXPECTED_START_OVERRIDES: dict[str, date] = {
    "husted-jon": date(2025, 1, 21),   # Vance -> Husted (OH)
    "moody-ashley": date(2025, 1, 21), # Rubio -> Moody (FL)
}


def load_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def fetch_coverage(conn) -> list[dict]:
    """One row per active senator with earliest/latest record + collector metadata."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            s.id,
            s.full_name,
            s.state,
            s.party,
            s.collection_method,
            s.requires_js,
            count(pr.id) FILTER (WHERE pr.deleted_at IS NULL)::int AS total,
            min(pr.published_at) FILTER (WHERE pr.deleted_at IS NULL)::date AS earliest,
            max(pr.published_at) FILTER (WHERE pr.deleted_at IS NULL)::date AS latest,
            count(*) FILTER (
              WHERE pr.deleted_at IS NULL
                AND pr.published_at >= '2025-01-01'
                AND pr.published_at < '2025-04-01'
            )::int AS q1_2025,
            count(*) FILTER (
              WHERE pr.deleted_at IS NULL
                AND pr.published_at >= date_trunc('month', now() - interval '60 days')
            )::int AS recent_60d
        FROM senators s
        LEFT JOIN press_releases pr ON pr.senator_id = s.id
        WHERE s.status = 'active'
        GROUP BY s.id, s.full_name, s.state, s.party,
                 s.collection_method, s.requires_js
        ORDER BY s.full_name
        """
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def classify(rows: list[dict], threshold_days: int) -> list[dict]:
    """Annotate rows with expected_start, gap_days, and severity."""
    out = []
    for r in rows:
        expected = EXPECTED_START_OVERRIDES.get(r["id"], DEFAULT_COVERAGE_START)
        earliest = r["earliest"]

        if earliest is None:
            severity = "NO_DATA" if r["total"] == 0 else "NO_DATES"
            gap_days = None
        else:
            gap_days = (earliest - expected).days
            if gap_days > threshold_days:
                severity = "TRUNCATED"
            elif gap_days > 14:
                severity = "SHALLOW"
            else:
                severity = "OK"

        out.append({
            **r,
            "expected_start": expected,
            "gap_days": gap_days,
            "severity": severity,
        })
    return out


def print_table(rows: list[dict]) -> None:
    header = f"{'SENATOR':<28} {'ST':<3} {'METHOD':<10} {'JS':<3} {'TOTAL':>5} {'EARLIEST':<11} {'EXPECT':<11} {'GAP':>5} {'Q1':>4} {'60d':>4} SEVERITY"
    print(header)
    print("-" * len(header))
    for r in rows:
        earliest = str(r["earliest"]) if r["earliest"] else "---"
        expected = str(r["expected_start"])
        gap = f"{r['gap_days']:>4}d" if r["gap_days"] is not None else "  ---"
        js = "Y" if r["requires_js"] else "."
        print(
            f"{r['id']:<28} {r['state']:<3} "
            f"{(r['collection_method'] or '-'):<10} {js:<3} "
            f"{r['total']:>5} {earliest:<11} {expected:<11} {gap:>5} "
            f"{r['q1_2025']:>4} {r['recent_60d']:>4} {r['severity']}"
        )


def summarize(rows: list[dict]) -> None:
    buckets: dict[str, int] = {}
    for r in rows:
        buckets[r["severity"]] = buckets.get(r["severity"], 0) + 1
    print()
    print("Summary by severity:")
    for sev in ("TRUNCATED", "SHALLOW", "OK", "NO_DATA", "NO_DATES"):
        n = buckets.get(sev, 0)
        if n:
            print(f"  {sev:<10} {n}")

    truncated = [r for r in rows if r["severity"] == "TRUNCATED"]
    if truncated:
        by_method: dict[str, int] = {}
        by_js: dict[str, int] = {}
        for r in truncated:
            m = r["collection_method"] or "unset"
            by_method[m] = by_method.get(m, 0) + 1
            k = "requires_js" if r["requires_js"] else "plain"
            by_js[k] = by_js.get(k, 0) + 1
        print()
        print("Truncated breakdown by method:")
        for m, n in sorted(by_method.items(), key=lambda x: -x[1]):
            print(f"  {m:<12} {n}")
        print("Truncated breakdown by JS:")
        for k, n in sorted(by_js.items(), key=lambda x: -x[1]):
            print(f"  {k:<12} {n}")


def run(threshold: int, show_all: bool, as_json: bool) -> int:
    load_env()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    rows = fetch_coverage(conn)
    conn.close()

    classified = classify(rows, threshold)

    if as_json:
        payload = [
            {
                **r,
                "earliest": r["earliest"].isoformat() if r["earliest"] else None,
                "latest": r["latest"].isoformat() if r["latest"] else None,
                "expected_start": r["expected_start"].isoformat(),
            }
            for r in classified
        ]
        print(json.dumps(payload, indent=2))
        return 0

    display = classified if show_all else [
        r for r in classified if r["severity"] in ("TRUNCATED", "SHALLOW", "NO_DATA", "NO_DATES")
    ]
    display.sort(key=lambda r: (
        r["severity"] != "TRUNCATED",       # TRUNCATED first
        -(r["gap_days"] or 0),               # biggest gap first
    ))

    print(f"Back-coverage check | threshold={threshold}d | "
          f"{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()
    if not display:
        print("  No truncated senators. All active senators reach their expected start.")
        summarize(classified)
        return 0

    print_table(display)
    summarize(classified)

    # Exit code: non-zero if any TRUNCATED so CI/cron can alert.
    truncated_count = sum(1 for r in classified if r["severity"] == "TRUNCATED")
    return 1 if truncated_count > 0 else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Back-coverage health check")
    ap.add_argument("--threshold", type=int, default=60,
                    help="Flag senators whose earliest record is >N days after expected start (default 60)")
    ap.add_argument("--all", action="store_true",
                    help="Show every active senator, not just flagged")
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON instead of a table")
    args = ap.parse_args()
    sys.exit(run(args.threshold, args.all, args.json))


if __name__ == "__main__":
    main()
