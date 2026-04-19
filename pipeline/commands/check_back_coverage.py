"""
Capitol Releases -- Coverage Audit (Script 8)

Per-senator data-integrity audit. Produces multiple signals and a single
confidence score (0-100%) summarizing how certain we are that we've
collected every press release for that senator in the window.

Three classes of failure this catches that aggregate tests miss:

1. TRUNCATED -- earliest record is >60 days after expected coverage start.
   Classic symptom of HTML pagination caps: Heinrich (NM) has 107
   records, all from Dec 2025 onward, with Jan-Nov 2025 silently gone.

2. DATE_CLUMPED -- total records are compressed onto a tiny number of
   unique publication dates. Scott-rick has 398 records on ~16 unique
   days, all bucketed to the 1st-of-month. The collector is fetching
   real content but failing to parse per-record dates, so everything
   falls back to the scrape date / month label.

3. INTERNAL_GAP -- an active senator has a multi-week stretch of zero
   posts inside their covered span. Can indicate date-parsing holes,
   session-expiry during a long scrape, or specific archive pages that
   weren't reachable.

Also reports SHALLOW (14-60d start gap), LOW_VOLUME (far below peer
median), and NO_DATA (zero records) as diagnostic categories.

Usage:
    python -m pipeline back-coverage                 # flagged senators
    python -m pipeline back-coverage --all           # every senator
    python -m pipeline back-coverage --threshold 30  # start-gap threshold (default 60d)
    python -m pipeline back-coverage --detail <id>   # weekly histogram for one senator
    python -m pipeline back-coverage --json          # machine-readable
"""
import argparse
import json
import os
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg2

DEFAULT_COVERAGE_START = date(2025, 1, 1)

EXPECTED_START_OVERRIDES: dict[str, date] = {
    "husted-jon": date(2025, 1, 21),
    "moody-ashley": date(2025, 1, 21),
}

# Round-number "too clean" check -- likely pagination caps.
ROUND_NUMBER_SET = {10, 20, 25, 30, 40, 50, 60, 75, 100, 150, 200, 250, 300}


def load_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def fetch_rows(conn) -> list[dict]:
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
            count(pr.id) FILTER (WHERE pr.deleted_at IS NULL
                                  AND pr.published_at >= '2025-01-01')::int AS total,
            count(DISTINCT pr.published_at::date)
                FILTER (WHERE pr.deleted_at IS NULL
                        AND pr.published_at >= '2025-01-01')::int AS unique_days,
            min(pr.published_at) FILTER (WHERE pr.deleted_at IS NULL
                                          AND pr.published_at >= '2025-01-01')::date AS earliest,
            max(pr.published_at) FILTER (WHERE pr.deleted_at IS NULL
                                          AND pr.published_at >= '2025-01-01')::date AS latest
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


def fetch_weekly_histogram(conn, senator_id: str) -> list[tuple[date, int]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT date_trunc('week', published_at)::date AS wk,
               count(*)::int
        FROM press_releases
        WHERE senator_id = %s
          AND deleted_at IS NULL
          AND published_at >= '2025-01-01'
        GROUP BY wk
        ORDER BY wk
        """,
        (senator_id,),
    )
    out = [(r[0], r[1]) for r in cur.fetchall()]
    cur.close()
    return out


def longest_zero_gap_weeks(weekly: list[tuple[date, int]], end: date) -> int:
    """Longest run of zero-post weeks between the first active week and `end`.

    Uses ISO weekday alignment via date_trunc('week', ...), which is Monday.
    """
    if not weekly:
        return 0
    weeks_with_posts = {w for w, _ in weekly}
    start = weekly[0][0]
    cur = start
    # Align end to Monday boundary.
    end_monday = end - timedelta(days=end.weekday())
    longest = 0
    run = 0
    while cur <= end_monday:
        if cur in weeks_with_posts:
            run = 0
        else:
            run += 1
            longest = max(longest, run)
        cur += timedelta(weeks=1)
    return longest


def classify_and_score(
    row: dict,
    threshold_days: int,
    peer_median: float,
    longest_gap_weeks: int,
    today: date,
) -> dict:
    total = row["total"]
    unique_days = row["unique_days"]
    earliest = row["earliest"]
    expected = EXPECTED_START_OVERRIDES.get(row["id"], DEFAULT_COVERAGE_START)

    if total == 0:
        return {
            **row,
            "expected_start": expected,
            "gap_days": None,
            "longest_gap_weeks": 0,
            "clump_ratio": None,
            "peer_ratio": 0.0,
            "severity": "NO_DATA",
            "confidence_pct": 0,
        }

    gap_days = (earliest - expected).days if earliest else None
    clump_ratio = unique_days / total if total else 0.0
    peer_ratio = total / peer_median if peer_median else 1.0
    round_flag = total in ROUND_NUMBER_SET

    # Severity in priority order.
    if gap_days is not None and gap_days > threshold_days:
        severity = "TRUNCATED"
    elif clump_ratio < 0.2 and total >= 30:
        severity = "DATE_CLUMPED"
    elif longest_gap_weeks >= 4 and total >= 30:
        severity = "INTERNAL_GAP"
    elif peer_ratio < 0.25:
        severity = "LOW_VOLUME"
    elif gap_days is not None and gap_days > 14:
        severity = "SHALLOW"
    else:
        severity = "OK"

    # Confidence score components (each in [0.1, 1.0]).
    coverage_start_score = 1 - clamp(max(0, (gap_days or 0) - 14) / 200, 0, 0.9)
    continuity_score = 1 - clamp(longest_gap_weeks / 16, 0, 0.7)
    volume_score = clamp(peer_ratio, 0.3, 1.0)
    date_quality_score = clamp(clump_ratio * 1.25, 0.3, 1.0)
    round_penalty = 0.9 if round_flag else 1.0
    clump_penalty = 0.5 if severity == "DATE_CLUMPED" else 1.0

    confidence = (
        coverage_start_score
        * continuity_score
        * volume_score
        * date_quality_score
        * round_penalty
        * clump_penalty
    )
    confidence = clamp(confidence, 0.05, 1.0)

    return {
        **row,
        "expected_start": expected,
        "gap_days": gap_days,
        "longest_gap_weeks": longest_gap_weeks,
        "clump_ratio": clump_ratio,
        "peer_ratio": peer_ratio,
        "severity": severity,
        "confidence_pct": round(confidence * 100),
    }


def print_table(rows: list[dict]) -> None:
    header = (
        f"{'SENATOR':<28} {'ST':<3} {'METHOD':<10} {'JS':<3} "
        f"{'TOTAL':>5} {'EARLIEST':<11} {'GAP':>5} {'ZEROW':>5} "
        f"{'UDAYS':>5} {'CLUMP':>6} {'PEER':>5} {'CONF':>5}  SEVERITY"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        earliest = str(r["earliest"]) if r["earliest"] else "---"
        gap = f"{r['gap_days']:>4}d" if r["gap_days"] is not None else "  ---"
        clump = f"{r['clump_ratio']:.2f}" if r["clump_ratio"] is not None else " ---"
        peer = f"{r['peer_ratio']:.2f}" if r.get("peer_ratio") is not None else " ---"
        js = "Y" if r["requires_js"] else "."
        print(
            f"{r['id']:<28} {r['state']:<3} "
            f"{(r['collection_method'] or '-'):<10} {js:<3} "
            f"{r['total']:>5} {earliest:<11} {gap:>5} "
            f"{r['longest_gap_weeks']:>5} {r['unique_days']:>5} "
            f"{clump:>6} {peer:>5} {r['confidence_pct']:>4}%  {r['severity']}"
        )


def print_detail(conn, senator_id: str, today: date) -> None:
    cur = conn.cursor()
    cur.execute(
        "SELECT id, full_name, state, party, collection_method, requires_js "
        "FROM senators WHERE id = %s",
        (senator_id,),
    )
    meta = cur.fetchone()
    cur.close()
    if not meta:
        print(f"No senator with id={senator_id}")
        return

    weekly = fetch_weekly_histogram(conn, senator_id)
    print(f"Senator: {meta[1]}  ({meta[2]}-{meta[3]})  method={meta[4]} requires_js={meta[5]}")
    if not weekly:
        print("  no in-window records")
        return

    total = sum(n for _, n in weekly)
    active_weeks = len(weekly)
    start = weekly[0][0]
    span = ((today - start).days // 7) + 1
    longest = longest_zero_gap_weeks(weekly, today)
    med = statistics.median(n for _, n in weekly)

    print(f"  Total: {total}   Active weeks: {active_weeks} / {span} span   "
          f"Median/active-week: {med}   Longest 0-week run: {longest}")
    print()
    print(f"  {'WEEK':<12} COUNT")
    max_n = max(n for _, n in weekly)
    for wk, n in weekly:
        bar = "#" * int(40 * n / max_n) if max_n else ""
        print(f"  {wk}   {n:>4}  {bar}")


def summarize(rows: list[dict]) -> None:
    buckets: dict[str, int] = {}
    conf_by_sev: dict[str, list[int]] = {}
    for r in rows:
        buckets[r["severity"]] = buckets.get(r["severity"], 0) + 1
        conf_by_sev.setdefault(r["severity"], []).append(r["confidence_pct"])

    print()
    print("Summary:")
    for sev in ("TRUNCATED", "DATE_CLUMPED", "INTERNAL_GAP", "LOW_VOLUME",
                "SHALLOW", "OK", "NO_DATA"):
        n = buckets.get(sev, 0)
        if n:
            scores = conf_by_sev.get(sev, [])
            avg = sum(scores) / len(scores) if scores else 0
            print(f"  {sev:<14} {n:>3}   avg conf {avg:>4.0f}%")

    all_conf = [r["confidence_pct"] for r in rows if r["total"] > 0]
    if all_conf:
        print()
        print(f"Overall confidence (active senators with data):")
        print(f"  mean   {statistics.mean(all_conf):>4.0f}%")
        print(f"  median {statistics.median(all_conf):>4.0f}%")
        print(f"  p10    {sorted(all_conf)[max(0, len(all_conf)//10 - 1)]:>4}%")


def run(threshold: int, show_all: bool, as_json: bool, detail: str | None) -> int:
    load_env()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    if detail:
        print_detail(conn, detail, date.today())
        conn.close()
        return 0

    raw = fetch_rows(conn)
    today = date.today()

    # Peer median = median total across active senators with data.
    totals = [r["total"] for r in raw if r["total"] > 0]
    peer_median = statistics.median(totals) if totals else 1.0

    classified = []
    for r in raw:
        longest = 0
        if r["total"] > 0:
            weekly = fetch_weekly_histogram(conn, r["id"])
            longest = longest_zero_gap_weeks(weekly, today)
        classified.append(classify_and_score(r, threshold, peer_median, longest, today))

    conn.close()

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
        print(json.dumps(payload, indent=2, default=str))
        return 0

    flag_sevs = {"TRUNCATED", "DATE_CLUMPED", "INTERNAL_GAP", "LOW_VOLUME",
                 "SHALLOW", "NO_DATA"}
    display = classified if show_all else [r for r in classified if r["severity"] in flag_sevs]
    sev_order = ["TRUNCATED", "DATE_CLUMPED", "INTERNAL_GAP", "LOW_VOLUME",
                 "SHALLOW", "NO_DATA", "OK"]
    display.sort(key=lambda r: (
        sev_order.index(r["severity"]),
        r["confidence_pct"],
    ))

    print(f"Coverage audit | threshold={threshold}d | peer_median={peer_median:.0f} | "
          f"{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()
    if not display:
        print("  No senators flagged. All active senators look fully covered.")
    else:
        print_table(display)

    summarize(classified)

    hard_fail = {"TRUNCATED", "DATE_CLUMPED"}
    hard_fail_count = sum(1 for r in classified if r["severity"] in hard_fail)
    return 1 if hard_fail_count > 0 else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Per-senator coverage audit")
    ap.add_argument("--threshold", type=int, default=60,
                    help="Start-gap threshold in days (default 60)")
    ap.add_argument("--all", action="store_true",
                    help="Show every active senator, not just flagged")
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON instead of a table")
    ap.add_argument("--detail", type=str, default=None,
                    help="Print weekly histogram for one senator_id and exit")
    args = ap.parse_args()
    sys.exit(run(args.threshold, args.all, args.json, args.detail))


if __name__ == "__main__":
    main()
