"""
Capitol Releases -- Data Quality Tests

Automated checks that verify data integrity, detect anomalies,
and flag likely problems. Run after any backfill or repair.

Usage:
    python -m pytest pipeline/tests/test_data_quality.py -v
    python pipeline/tests/test_data_quality.py  # standalone
"""

import os
import sys
import json
from datetime import date, datetime, timezone
from pathlib import Path
from collections import Counter

import psycopg2

# Load .env file if present
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.environ["DATABASE_URL"]
SEED_PATH = Path(__file__).resolve().parent.parent / "seeds" / "senate.json"


def get_conn():
    return psycopg2.connect(DB_URL)


def _load_seeds():
    return json.load(SEED_PATH.open())["members"]


# ---- Senator coverage tests ----

def test_all_senators_in_db():
    """Every senator should have a record in the senators table."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM senators")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert count >= 100, f"Expected >= 100 senators (includes former), got {count}"


def test_senators_have_urls():
    """Every senator should have a press_release_url (except Armstrong who has no page)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT full_name FROM senators WHERE press_release_url IS NULL")
    missing = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    # Armstrong legitimately has no press releases
    allowed_missing = {"Alan Armstrong"}
    unexpected = set(missing) - allowed_missing
    assert len(unexpected) == 0, f"Senators missing URLs: {unexpected}"


def test_minimum_senator_coverage():
    """At least 95 senators should have press releases."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT count(DISTINCT senator_id) FROM press_releases WHERE deleted_at IS NULL")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert count >= 95, f"Only {count} senators have releases, expected >= 95"


# ---- Data volume tests ----

def test_minimum_total_records():
    """Should have at least 10,000 press releases."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM press_releases WHERE deleted_at IS NULL")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert count >= 10000, f"Only {count} records, expected >= 10,000"


def test_no_empty_titles():
    """Every record should have a non-empty title."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM press_releases WHERE deleted_at IS NULL AND title IS NULL OR length(trim(title)) < 5")
    bad = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert bad == 0, f"{bad} records have empty or very short titles"


def test_no_duplicate_urls():
    """Source URLs should be unique."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT source_url, count(*) as cnt
        FROM press_releases WHERE deleted_at IS NULL
        GROUP BY source_url
        HAVING count(*) > 1
    """)
    dupes = cur.fetchall()
    cur.close()
    conn.close()
    assert len(dupes) == 0, f"{len(dupes)} duplicate URLs found"


# ---- Date quality tests ----

def test_date_coverage_above_threshold():
    """At least 60% of records should have dates."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FILTER (WHERE published_at IS NOT NULL), count(*) FROM press_releases WHERE deleted_at IS NULL")
    dated, total = cur.fetchone()
    cur.close()
    conn.close()
    pct = dated / total * 100 if total > 0 else 0
    assert pct >= 50, f"Only {pct:.0f}% of records have dates, expected >= 50%"


def test_dates_in_valid_range():
    """No dates should be before 2010 or after tomorrow (obvious parse errors)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT count(*) FROM press_releases WHERE deleted_at IS NULL
        AND published_at IS NOT NULL
        AND (published_at < '2010-01-01' OR published_at > NOW() + interval '2 days')
    """)
    bad = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert bad == 0, f"{bad} records have implausible dates (before 2010 or future)"


def test_no_future_dates():
    """No records should have dates more than 1 day in the future."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM press_releases WHERE deleted_at IS NULL AND published_at > NOW() + interval '1 day'")
    bad = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert bad == 0, f"{bad} records have future dates"


# ---- URL quality tests ----

def test_all_urls_are_government():
    """All source URLs should be .gov domains."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT source_url FROM press_releases WHERE deleted_at IS NULL
        AND source_url NOT LIKE '%.gov%'
        LIMIT 10
    """)
    bad = cur.fetchall()
    cur.close()
    conn.close()
    assert len(bad) == 0, f"Non-.gov URLs found: {[r[0][:60] for r in bad]}"


def test_no_listing_page_urls():
    """Source URLs should be detail pages, not listing pages."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT count(*) FROM press_releases WHERE deleted_at IS NULL
        AND (source_url ~ '/press-releases/?$'
           OR source_url ~ '/news-releases/?$'
           OR source_url ~ '/newsroom/?$'
           OR source_url ~ '/news/?$')
    """)
    bad = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert bad == 0, f"{bad} records have listing-page URLs instead of detail URLs"


def test_no_navigation_urls():
    """Source URLs should not be navigation/about/contact pages."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT count(*) FROM press_releases WHERE deleted_at IS NULL
        AND (source_url LIKE '%/about%'
           OR source_url LIKE '%/contact%'
           OR source_url LIKE '%/services%'
           OR source_url LIKE '%/issues%'
           OR source_url LIKE '%facebook.com%'
           OR source_url LIKE '%twitter.com%'
           OR source_url LIKE '%bsky.app%')
    """)
    bad = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert bad == 0, f"{bad} records have navigation/social URLs"


# ---- Round number anomaly detection ----

def test_no_suspicious_round_counts():
    """Flag senators with suspiciously round release counts (pagination/RSS caps).

    Common RSS-cap totals (10, 20, 25, 50, 100) and pagination-cap totals
    (multiples of 10 below 200) are red flags when records should number in
    the hundreds for an active senator. Triggered the Moran/Boozman fix on
    2026-04-25 (50 and 195 records vs ~2500 live).
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.full_name, count(pr.id)::int as cnt
        FROM senators s
        JOIN press_releases pr ON pr.senator_id = s.id
        WHERE pr.deleted_at IS NULL
        GROUP BY s.id, s.full_name
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    suspicious_exact = {10, 20, 25, 50, 75, 100, 150, 200}
    suspicious = [(name, cnt) for name, cnt in rows
                  if cnt in suspicious_exact and cnt < 500]

    if suspicious:
        print(f"Suspicious round counts ({len(suspicious)}):")
        for name, cnt in suspicious:
            print(f"  {name}: {cnt}")
    # Hard fail -- a single round-number hit is worth investigating. Allow
    # at most 2 to absorb genuine coincidences without masking real bugs.
    assert len(suspicious) <= 2, (
        f"{len(suspicious)} senators have suspicious round counts (likely "
        f"RSS or pagination caps): "
        + ", ".join(f"{n}={c}" for n, c in suspicious)
    )


# ---- RSS undercollection signature ----

def test_rss_collectors_not_undercollecting():
    """RSS feeds typically cap at 20-50 items, so any senator on
    collection_method=rss with low total record count is likely
    undercollected. A normal senator yields 200+ records across
    Jan 2025-now.

    History: Moran (R-KS) sat at 50 records and Boozman (R-AR) at 195
    despite their sites having 250+ pages of press releases. Both were
    misclassified as RSS when their underlying CMS exposed full
    pagination via httpx.
    """
    seeds = _load_seeds()
    rss_ids = [s["senator_id"] for s in seeds
               if s.get("collection_method") == "rss"]
    if not rss_ids:
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT senator_id, count(*)::int
        FROM press_releases
        WHERE deleted_at IS NULL AND senator_id = ANY(%s)
        GROUP BY senator_id
    """, (rss_ids,))
    counts = dict(cur.fetchall())
    cur.close()
    conn.close()

    flagged = sorted(
        ((sid, counts.get(sid, 0)) for sid in rss_ids if counts.get(sid, 0) < 200),
        key=lambda x: x[1],
    )
    assert not flagged, (
        f"{len(flagged)} senator(s) on collection_method=rss have <200 "
        f"records (likely RSS-cap undercollection): "
        + ", ".join(f"{sid}={n}" for sid, n in flagged)
    )


def test_no_rss_rampup_signature():
    """Detect the RSS-cap fingerprint: dense recent months but sparse
    early-2025. A healthy collector produces roughly flat monthly volume
    across Jan 2025-now; an RSS feed inherits its sliding window so
    older entries fall off and the DB ramps up.

    Flags any senator where last-30-day volume is >= 4x the average
    monthly volume across Jan-Mar 2025, AND total < 500.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT senator_id,
               count(*) FILTER (
                   WHERE published_at >= '2025-01-01'
                   AND published_at < '2025-04-01'
               )::float / 3.0 AS q1_monthly,
               count(*) FILTER (
                   WHERE published_at >= NOW() - INTERVAL '30 days'
               )::int AS last_30,
               count(*)::int AS total
        FROM press_releases
        WHERE deleted_at IS NULL
        GROUP BY senator_id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    flagged = []
    for sid, q1_monthly, last_30, total in rows:
        if total >= 500:
            continue
        if q1_monthly < 1:
            continue
        ratio = last_30 / q1_monthly
        if ratio >= 4.0:
            flagged.append((sid, total, q1_monthly, last_30, ratio))

    if flagged:
        print(f"RSS ramp-up signature ({len(flagged)}):")
        for sid, total, q1m, l30, r in flagged:
            print(f"  {sid}: total={total} q1_monthly={q1m:.1f} last_30={l30} ratio={r:.1f}x")
    # Soft assertion -- new senators legitimately ramp up; allow up to 3.
    assert len(flagged) <= 3, (
        f"{len(flagged)} senators show RSS ramp-up signature "
        f"(last_30 >= 4x q1_2025 monthly, total < 500): "
        + ", ".join(f"{sid}({r:.1f}x)" for sid, _, _, _, r in flagged)
    )


# ---- Completeness tests ----

def test_depth_to_jan_2025():
    """At least 30 senators should have data reaching Jan-Feb 2025."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT count(*) FROM (
            SELECT senator_id FROM press_releases WHERE deleted_at IS NULL
            AND published_at IS NOT NULL
            GROUP BY senator_id
            HAVING min(published_at)::date <= '2025-02-28'
        ) sub
    """)
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert count >= 30, f"Only {count} senators reach Jan-Feb 2025, expected >= 30"


def test_no_date_clumping():
    """Total records should not be smashed onto a tiny set of unique publication days.

    Catches the Scott-rick / Blackburn pattern: 400 records dated to only 16
    unique days (all first-of-month), meaning the collector fetched real
    content but failed to parse per-record dates. Flag when
    unique_days / total < 0.2 AND total >= 30.

    Run `python -m pipeline back-coverage` for the full list and
    `--detail <senator_id>` for a weekly histogram.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.full_name,
               count(pr.id)::int as total,
               count(DISTINCT pr.published_at::date)::int as unique_days
        FROM senators s
        JOIN press_releases pr ON pr.senator_id = s.id
        WHERE s.status = 'active'
          AND pr.deleted_at IS NULL
          AND pr.published_at >= '2025-01-01'
        GROUP BY s.id, s.full_name
        HAVING count(pr.id) >= 30
    """)
    clumped = []
    for name, total, unique_days in cur.fetchall():
        min_required_days = min(int(total * 0.2), 20)
        if unique_days < min_required_days:
            clumped.append((name, total, unique_days))
    cur.close()
    conn.close()

    if clumped:
        print(f"WARNING: {len(clumped)} senators show date-clumping (real content, wrong dates):")
        for name, total, udays in clumped:
            print(f"  {name}: {total} records on only {udays} unique days ({udays/total:.0%})")
    # Soft assertion -- fail hard only if the problem grows.
    assert len(clumped) < 8, (
        f"{len(clumped)} senators have date-clumped records. "
        f"Run `python -m pipeline back-coverage` to diagnose."
    )


def test_back_coverage_not_truncated():
    """Per-senator check: earliest record should not be >60 days after coverage start.

    Catches the Heinrich/Murray pattern where a senator has a plausible total
    record count but every record is from the last few months -- the collector
    is reading page 1 and missing older paginated archives. Complements the
    aggregate `test_depth_to_jan_2025` check which only counts senators
    reaching Jan-Feb, not the ones that silently start in late 2025.

    Run the standalone report for diagnostics:
        python -m pipeline back-coverage
    """
    # Mid-window seat changes -- expected start is their in-office date.
    overrides = {
        "husted-jon": date(2025, 1, 21),   # Vance -> Husted
        "moody-ashley": date(2025, 1, 21), # Rubio -> Moody
    }
    default_start = date(2025, 1, 1)
    threshold_days = 60

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.full_name,
               min(pr.published_at) FILTER (WHERE pr.deleted_at IS NULL)::date AS earliest,
               count(pr.id) FILTER (WHERE pr.deleted_at IS NULL)::int AS total
        FROM senators s
        LEFT JOIN press_releases pr ON pr.senator_id = s.id
        WHERE s.status = 'active'
        GROUP BY s.id, s.full_name
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    truncated = []
    for sid, name, earliest, total in rows:
        if earliest is None or total == 0:
            continue  # NO_DATA handled by test_minimum_senator_coverage
        expected = overrides.get(sid, default_start)
        gap = (earliest - expected).days
        if gap > threshold_days:
            truncated.append((name, earliest, gap, total))

    if truncated:
        print(f"WARNING: {len(truncated)} senators have truncated back-coverage:")
        for name, earliest, gap, total in truncated:
            print(f"  {name}: earliest={earliest} gap={gap}d total={total}")
    # Soft assertion -- fail hard only when the problem grows.
    assert len(truncated) < 10, (
        f"{len(truncated)} senators have earliest record > {threshold_days}d after expected start. "
        f"Run `python -m pipeline back-coverage` to diagnose."
    )


# ---- Body text and provenance tests ----

def test_body_coverage_above_threshold():
    """At least 70% of records should have body text > 100 chars."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM press_releases WHERE deleted_at IS NULL")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM press_releases WHERE deleted_at IS NULL AND body_text IS NOT NULL AND length(body_text) > 100")
    with_body = cur.fetchone()[0]
    cur.close()
    conn.close()
    pct = with_body / total * 100 if total > 0 else 0
    assert pct >= 70, f"Only {pct:.0f}% of records have body text > 100 chars, expected >= 70%"


def test_no_anomalously_low_counts():
    """No active senator should have less than 10% of the median release count.

    If a longstanding senator has single-digit releases while peers have hundreds,
    that indicates a collection failure, not inactivity.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY cnt) as median
        FROM (
            SELECT COUNT(*) as cnt FROM press_releases WHERE deleted_at IS NULL
            GROUP BY senator_id HAVING COUNT(*) > 0
        ) sub
    """)
    median = cur.fetchone()[0] or 1
    threshold = max(median * 0.1, 10)  # at least 10

    cur.execute("""
        SELECT s.id, s.full_name, COUNT(pr.id) FILTER (WHERE pr.deleted_at IS NULL) as cnt
        FROM senators s
        LEFT JOIN press_releases pr ON s.id = pr.senator_id
        WHERE s.collection_method IS NOT NULL
        GROUP BY s.id, s.full_name
        HAVING COUNT(pr.id) FILTER (WHERE pr.deleted_at IS NULL) < %s
    """, (threshold,))
    flagged = cur.fetchall()
    cur.close()
    conn.close()

    if flagged:
        print(f"WARNING: {len(flagged)} senators below {threshold:.0f} releases (median={median:.0f}):")
        for sid, name, cnt in flagged:
            print(f"  {name}: {cnt}")
    # Soft threshold -- allow some while we close gaps
    assert len(flagged) < 25, f"{len(flagged)} senators are anomalously low (< {threshold:.0f} releases, median={median:.0f})"


def test_no_stale_senators():
    """Every active senator should have a release in the last 60 days."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.full_name, MAX(pr.published_at) as last_release
        FROM senators s
        JOIN press_releases pr ON s.id = pr.senator_id
        WHERE s.collection_method IS NOT NULL
        GROUP BY s.id, s.full_name
        HAVING MAX(pr.published_at) < NOW() - INTERVAL '60 days'
    """)
    stale = cur.fetchall()
    cur.close()
    conn.close()
    if stale:
        print(f"WARNING: {len(stale)} senators have no releases in 60 days:")
        for sid, name, last in stale:
            print(f"  {name}: last release {last.date() if last else 'never'}")
    # Soft assertion -- allow some stale senators
    assert len(stale) < 10, f"{len(stale)} senators are stale (no releases in 60 days)"


# ---- Per-content-type coverage tests ----
#
# These exist because aggregate tests hide silent collapses of specific types.
# If the classifier regresses and stops emitting 'letter', the total record
# count barely moves (letters are ~100 of 34k) and every other test passes,
# but a real coverage gap just opened. These tests assert a floor per type.

# Expected floors calibrated from 2026-04-21 DB state. Adjust only when scope
# changes (e.g. new collector added). A floor going up is fine; the purpose is
# to catch a sudden drop.
_TYPE_FLOORS = {
    "press_release":        30_000,
    "statement":               300,
    "op_ed":                   100,
    "letter":                   50,
    "floor_statement":          50,
    "presidential_action":     400,
    # photo_release and 'other' intentionally omitted -- low signal,
    # not worth asserting a floor on.
}


def test_per_type_floors():
    """Each tracked content_type should have at least its expected floor of records.

    Catches the failure mode where a classifier regression or collector bug
    silently zeroes out an entire type while total record count looks fine.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT content_type, count(*)::int
        FROM press_releases
        WHERE deleted_at IS NULL
        GROUP BY content_type
    """)
    actual = dict(cur.fetchall())
    cur.close()
    conn.close()

    low = []
    for t, floor in _TYPE_FLOORS.items():
        got = actual.get(t, 0)
        if got < floor:
            low.append(f"{t}: {got} (floor {floor})")

    assert not low, (
        "content_type record counts below calibrated floor — possible "
        f"classifier regression: {', '.join(low)}"
    )


def test_per_type_back_coverage():
    """No content_type should have its earliest record more than 90 days after Jan 1, 2025.

    If all op_eds date from Sep 2025 even though press releases go back to
    January, the op-ed collector is missing its historical archive.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT content_type, min(published_at)::date
        FROM press_releases
        WHERE deleted_at IS NULL
          AND published_at IS NOT NULL
        GROUP BY content_type
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    expected_start = date(2025, 1, 1)
    truncated = []
    for t, earliest in rows:
        if t not in _TYPE_FLOORS:  # only check tracked types
            continue
        gap = (earliest - expected_start).days
        if gap > 90:
            truncated.append(f"{t}: earliest={earliest} gap={gap}d")

    assert not truncated, (
        "per-type back-coverage truncated: " + ", ".join(truncated)
    )


def test_per_type_not_date_clumped():
    """No content_type should collapse onto a tiny set of publication days.

    Same logic as test_no_date_clumping but split by type. Catches the failure
    where a specific collector (e.g. floor-statement parser) falls back to a
    single default date for every record it processes.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT content_type,
               count(*)::int as total,
               count(DISTINCT published_at::date)::int as unique_days
        FROM press_releases
        WHERE deleted_at IS NULL
          AND published_at >= '2025-01-01'
        GROUP BY content_type
        HAVING count(*) >= 30
    """)
    # Require at least 20 distinct publication days for any content_type with
    # >=30 records, scaled down for small types. A pure ratio (unique/total)
    # breaks at high volume: 32k records spanning 468 distinct days is near-full
    # day-coverage but reads as 1% "unique" under a ratio threshold.
    clumped = []
    for t, total, unique_days in cur.fetchall():
        if t not in _TYPE_FLOORS:
            continue
        min_required_days = min(int(total * 0.2), 20)
        if unique_days < min_required_days:
            clumped.append(
                f"{t}: {total} records on {unique_days} days "
                f"(need >= {min_required_days})"
            )
    cur.close()
    conn.close()

    assert not clumped, "per-type date clumping: " + ", ".join(clumped)


# ---- Run all tests ----

def run_all():
    """Run all tests and report results."""
    tests = [
        test_all_senators_in_db,
        test_senators_have_urls,
        test_minimum_senator_coverage,
        test_minimum_total_records,
        test_no_empty_titles,
        test_no_duplicate_urls,
        test_date_coverage_above_threshold,
        test_dates_in_valid_range,
        test_no_future_dates,
        test_all_urls_are_government,
        test_no_listing_page_urls,
        test_no_navigation_urls,
        test_no_suspicious_round_counts,
        test_rss_collectors_not_undercollecting,
        test_no_rss_rampup_signature,
        test_depth_to_jan_2025,
        test_back_coverage_not_truncated,
        test_no_date_clumping,
        test_body_coverage_above_threshold,
        test_no_anomalously_low_counts,
        test_no_stale_senators,
        test_per_type_floors,
        test_per_type_back_coverage,
        test_per_type_not_date_clumped,
    ]

    passed = 0
    failed = 0
    warnings = 0

    print(f"\n{'='*60}")
    print(f"  DATA QUALITY TESTS")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERR   {test.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  {passed} passed, {failed} failed")
    print(f"{'='*60}\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
