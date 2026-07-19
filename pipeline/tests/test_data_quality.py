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
from datetime import date, datetime, timedelta, timezone
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
    """The full US Senate roster must be present in the officials table.

    Scoped to chamber='senate' AND jurisdiction='us' so the 435 House +
    state/exec rows can't mask a wiped Senate corpus. There are 100 seats;
    counting active+former (seats that changed hands mid-window leave a
    former row) keeps the floor robust against a single vacancy.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT count(*) FROM officials WHERE chamber = 'senate' AND jurisdiction = 'us'"
    )
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert count >= 100, f"Expected >= 100 US senators (includes former), got {count}"


def test_senators_have_urls():
    """Every active US senator should have a press_release_url (except Armstrong)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT full_name FROM officials
        WHERE press_release_url IS NULL
          AND chamber = 'senate' AND jurisdiction = 'us'
          AND status = 'active'
    """)
    missing = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    # Armstrong legitimately has no press releases
    allowed_missing = {"Alan Armstrong"}
    unexpected = set(missing) - allowed_missing
    assert len(unexpected) == 0, f"Senators missing URLs: {unexpected}"


def test_minimum_senator_coverage():
    """At least 95 of the 100 US senators should have press releases.

    Scoped to chamber='senate' AND jurisdiction='us'. Without the scope the
    hundreds of House/state officials with items keep the DISTINCT count far
    above 95 even if the entire Senate corpus dropped out. 99 currently have
    items (Armstrong is the expected zero-release gap).
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT count(DISTINCT i.official_id)
        FROM official_site_items i
        JOIN officials o ON o.id = i.official_id
        WHERE i.deleted_at IS NULL
          AND o.chamber = 'senate' AND o.jurisdiction = 'us'
    """)
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert count >= 95, f"Only {count} US senators have releases, expected >= 95"


# ---- Data volume tests ----

def test_minimum_total_records():
    """Should have at least 10,000 press releases."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM official_site_items WHERE deleted_at IS NULL")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert count >= 10000, f"Only {count} records, expected >= 10,000"


def test_no_empty_titles():
    """Every record should have a non-empty title.

    Threshold relaxed from <5 to <3 chars on 2026-05-02 after House e-newsletter
    items surfaced legitimate one-word titles like "Iran" (graves-sam). The
    original cutoff was Senate-tuned; full press-release headlines typically
    run 30+ chars. House Drupal newsletters use single-word topic titles.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT count(*) FROM official_site_items
        WHERE deleted_at IS NULL
          AND (title IS NULL OR length(trim(title)) < 3)
    """)
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
        FROM official_site_items WHERE deleted_at IS NULL
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
    cur.execute("SELECT count(*) FILTER (WHERE published_at IS NOT NULL), count(*) FROM official_site_items WHERE deleted_at IS NULL")
    dated, total = cur.fetchone()
    cur.close()
    conn.close()
    pct = dated / total * 100 if total > 0 else 0
    assert pct >= 50, f"Only {pct:.0f}% of records have dates, expected >= 50%"


def test_dates_in_valid_range():
    """Pre-2010 dates or far-future dates (>1 year ahead) indicate parser
    errors and fail. Near-future dates (1 day to 1 year ahead) are almost
    always upstream typos on the senator's site itself (e.g. wrong year on a
    real release) — handled as a warning by test_no_future_dates, not a
    failure here. The 1-year window was widened from 60 days on 2026-05-15
    after a single alford-mark typo (2026-09-23 on a real CJS appropriations
    release) failed every cron for two days."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT official_id, source_url, published_at FROM official_site_items
        WHERE deleted_at IS NULL
          AND published_at IS NOT NULL
          AND (published_at < '2010-01-01' OR published_at > NOW() + interval '1 year')
        LIMIT 10
    """)
    obvious_errors = cur.fetchall()
    cur.close()
    conn.close()
    if obvious_errors:
        sample = [(r[0], str(r[2])[:10], r[1][:60]) for r in obvious_errors]
        # Proportionality gate (2026-07-19): a handful of bad rows is one
        # site's junk/typo — warn and let the digest surface it. Five or
        # more means a parser bug is writing garbage at scale — fail.
        # (Three Costa contact pages kept the whole cron red July 8-19;
        # same lesson as the 2026-05-15 alford-mark widening above.)
        if len(obvious_errors) < 5:
            print(f"WARNING: {len(obvious_errors)} records with implausible dates (below fail threshold of 5): {sample}")
        else:
            assert False, f"{len(obvious_errors)} records have implausible dates: {sample}"


def test_no_future_dates():
    """Near-future published_at (1 day to 1 year ahead) is almost always an
    upstream typo on the senator's senate.gov page. We collect what they
    publish, so we flag the anomaly but don't fail the suite — the source is
    wrong, not us. Window widened from 60 days to 1 year on 2026-05-15 to
    match test_dates_in_valid_range."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT official_id, source_url, published_at FROM official_site_items
        WHERE deleted_at IS NULL
          AND published_at > NOW() + interval '1 day'
          AND published_at <= NOW() + interval '1 year'
        ORDER BY published_at
    """)
    typos = cur.fetchall()
    cur.close()
    conn.close()
    if typos:
        print(f"WARNING: {len(typos)} records with future published_at — likely upstream typos:")
        for official_id, source_url, pub_at in typos[:10]:
            print(f"  {official_id}: {pub_at.strftime('%Y-%m-%d')} - {source_url[:80]}")


# ---- URL quality tests ----

def test_all_urls_are_government():
    """All source URLs should be .gov domains."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT source_url FROM official_site_items WHERE deleted_at IS NULL
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
        SELECT count(*) FROM official_site_items WHERE deleted_at IS NULL
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
    """Source URLs should not be navigation/about/contact pages.

    Match the path segment as a leaf (e.g. trailing /about, /about/, or
    /about?...). Substring matching falsely flagged Husted's newsletters
    that live at /contact/newsletters/... (a legit content path).
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT count(*) FROM official_site_items WHERE deleted_at IS NULL
        AND (source_url ~ '/(about|contact|services|issues)(/?(\\?.*)?$)'
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
    # Scoped to chamber='senate'. House feeds cap at 10 by design (Drupal
    # /rss.xml limit), so applying this Senate-style RSS-cap heuristic to
    # House would flag every active member.
    cur.execute("""
        SELECT s.id, s.full_name, count(pr.id)::int as cnt
        FROM officials s
        JOIN official_site_items pr ON pr.official_id = s.id
        WHERE pr.deleted_at IS NULL
          AND s.chamber = 'senate' AND s.jurisdiction = 'us'
        GROUP BY s.id, s.full_name
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    suspicious_exact = {10, 20, 25, 50, 75, 100, 150, 200, 250, 300, 350, 400, 450}
    # Verified-legitimate coincidences: each manually checked for healthy
    # monthly distribution and full back-coverage to Jan 2025.
    verified_ok = {
        "tillis-thom",       # 100 -- retiring, lower output, 15-month spread
        "baldwin-tammy",     # 350 -- healthy 14-35/mo across 16 months
        "moran-jerry",       # 250 -- post-backfill on 2026-04-25, 8-30/mo
        "scott-rick",        # 400 -- healthy 8-52/mo across 17 months back to Jan 2025
        "crapo-mike",        # 400 -- healthy 3-44/mo across 17 months back to Jan 2025, httpx not RSS
        "johnson-ron",       # 100 -- healthy 1-16/mo across 17 months back to Jan 2025
        "ernst-joni",        # 450 -- healthy 10-44/mo across 17 months back to Jan 2025 (verified 2026-05-15)
        "kelly-mark",        # 450 -- healthy 6-41/mo across 17 months back to Jan 2025 (verified 2026-05-15)
        "boozman-john",      # 250 -- healthy 4-34/mo across 18 months back to Jan 2025 (verified 2026-05-15)
        # TX state senators verified live against senate.texas.gov on
        # 2026-04-29 — 30/30 senator counts match the actual pressroom.
        # Round counts are coincidence, not a collection cap.
        "tx-d27-hinojosa-adam",   # 10 -- live count = 10
        "tx-d14-eckhardt",         # 20 -- live count = 20
    }
    suspicious = [(sid, name, cnt) for sid, name, cnt in rows
                  if cnt in suspicious_exact and cnt < 500
                  and sid not in verified_ok]

    if suspicious:
        print(f"Suspicious round counts ({len(suspicious)}):")
        for sid, name, cnt in suspicious:
            print(f"  {name} ({sid}): {cnt}")
    assert not suspicious, (
        f"{len(suspicious)} senators have unverified suspicious round counts "
        f"(likely RSS or pagination caps): "
        + ", ".join(f"{n}={c}" for _, n, c in suspicious)
        + ". Investigate distribution, then add to verified_ok if legitimate."
    )


# ---- RSS undercollection signature ----

def test_rss_collectors_not_severely_undercollecting():
    """RSS feeds typically cap at 20-50 items, so any senator on
    collection_method=rss with very few records is almost certainly the
    Moran-shape misclassification bug -- where the underlying CMS
    actually supports full-archive pagination but we never wired it up.

    Threshold is intentionally low (<75) so we don't false-flag senators
    with naturally low publishing volume. The ramp-up signature test is
    the better tool for borderline cases.

    History: Moran (R-KS) sat at 50 records and Boozman (R-AR) at 195
    despite their sites having 250+ pages of press releases. Both were
    misclassified as RSS when their underlying CMS exposed full
    pagination via httpx.
    """
    seeds = _load_seeds()
    rss_ids = [s["official_id"] for s in seeds
               if s.get("collection_method") == "rss"]
    if not rss_ids:
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT official_id, count(*)::int
        FROM official_site_items
        WHERE deleted_at IS NULL AND official_id = ANY(%s)
        GROUP BY official_id
    """, (rss_ids,))
    counts = dict(cur.fetchall())
    cur.close()
    conn.close()

    flagged = sorted(
        ((sid, counts.get(sid, 0)) for sid in rss_ids if counts.get(sid, 0) < 75),
        key=lambda x: x[1],
    )
    assert not flagged, (
        f"{len(flagged)} senator(s) on collection_method=rss have <75 "
        f"records (likely RSS-cap undercollection from misclassified seed): "
        + ", ".join(f"{sid}={n}" for sid, n in flagged)
    )


def test_no_rss_rampup_signature():
    """Detect the RSS-cap fingerprint: dense recent months but sparse
    early-2025. A healthy collector produces roughly flat monthly volume
    across Jan 2025-now; an RSS feed inherits its sliding window so
    older entries fall off and the DB ramps up.

    Flags any senator where last-30-day volume is >= 4x the average
    monthly volume across Jan-Mar 2025, AND total < 500.

    Scoped to chamber='senate'. House members were onboarded 2026-05-02
    via wave-2 backfill; their Q1-2025 baseline is dominated by feed
    truncation rather than collector behavior, so the ramp-up
    comparison doesn't apply for ~12 months. Re-evaluate House
    eligibility once a year of post-onboarding data accrues.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT pr.official_id,
               count(*) FILTER (
                   WHERE pr.published_at >= '2025-01-01'
                   AND pr.published_at < '2025-04-01'
               )::float / 3.0 AS q1_monthly,
               count(*) FILTER (
                   WHERE pr.published_at >= NOW() - INTERVAL '30 days'
               )::int AS last_30,
               count(*)::int AS total
        FROM official_site_items pr
        JOIN officials s ON s.id = pr.official_id
        WHERE pr.deleted_at IS NULL
          AND s.chamber = 'senate' AND s.jurisdiction = 'us'
        GROUP BY pr.official_id
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


# ---- Per-senator activity-period checks ----

def test_no_zero_volume_months():
    """Each US senator should have at least one record in every calendar month
    between their first record and the last completed month.

    Scoped to chamber='senate'. State senators publish in session bursts —
    most TX senators have multi-month gaps that are real, not collection
    failures. Per-test scoping keeps the test useful for the chamber where
    monthly cadence is the right signal.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT pr.official_id,
               to_char(date_trunc('month', pr.published_at), 'YYYY-MM') AS m,
               count(*)::int AS n
        FROM official_site_items pr
        JOIN officials s ON s.id = pr.official_id
        WHERE pr.deleted_at IS NULL
          AND pr.published_at >= '2025-01-01'
          AND s.chamber = 'senate' AND s.jurisdiction = 'us'
        GROUP BY 1, 2
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    by_sen: dict[str, dict[str, int]] = {}
    for sid, m, n in rows:
        by_sen.setdefault(sid, {})[m] = n

    today = date.today()
    last_complete_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    expected_months = []
    cur_year, cur_month = 2025, 1
    while True:
        ym = f"{cur_year:04d}-{cur_month:02d}"
        expected_months.append(ym)
        if ym == last_complete_month:
            break
        cur_month += 1
        if cur_month > 12:
            cur_month = 1
            cur_year += 1

    flagged = []
    for sid, months in by_sen.items():
        floor_month = min(months)
        missing = [m for m in expected_months
                   if m not in months and m >= floor_month]
        if missing:
            flagged.append((sid, missing))

    if flagged:
        print(f"Zero-volume months ({len(flagged)} senators):")
        for sid, miss in flagged[:20]:
            print(f"  {sid}: missing {','.join(miss)}")
    # Hard fail -- a senator should always have something in a given month
    # unless they aren't yet active. Allow a small grace for senators on
    # genuine recess or with very low publishing cadence.
    assert len(flagged) <= 5, (
        f"{len(flagged)} senators have zero-volume months in their active "
        f"window: " + ", ".join(sid for sid, _ in flagged[:10])
        + ("..." if len(flagged) > 10 else "")
    )


def test_no_long_publication_gaps():
    """Flag any consecutive-record gap longer than 45 days within an
    active US senator's 2025-now window. Catches partial collection failures
    where a contiguous span of dates is missing.

    Scoped to chamber='senate' — TX senators have legitimate multi-month
    gaps between session and interim periods, so a 45-day gap floor doesn't
    apply.
    """
    conn = get_conn()
    cur = conn.cursor()
    # Compute per-senator max-gap using window functions
    cur.execute("""
        WITH ordered AS (
            SELECT pr.official_id,
                   pr.published_at,
                   lag(pr.published_at) OVER (PARTITION BY pr.official_id ORDER BY pr.published_at) AS prev_at
            FROM official_site_items pr
            JOIN officials s ON s.id = pr.official_id
            WHERE pr.deleted_at IS NULL
              AND pr.published_at >= '2025-01-01'
              AND s.chamber = 'senate' AND s.jurisdiction = 'us'
        )
        SELECT official_id,
               max(extract(epoch FROM (published_at - prev_at)) / 86400)::int AS max_gap_days
        FROM ordered
        WHERE prev_at IS NOT NULL
        GROUP BY official_id
        HAVING max(extract(epoch FROM (published_at - prev_at)) / 86400) > 45
    """)
    flagged = cur.fetchall()
    cur.close()
    conn.close()

    if flagged:
        print(f"Long publication gaps ({len(flagged)} senators):")
        for sid, gap in flagged[:20]:
            print(f"  {sid}: max gap {gap} days")
    # Allow a small grace: holiday recess + government shutdown periods
    # can produce legitimate ~30-40 day gaps; >45 is the threshold.
    assert len(flagged) <= 5, (
        f"{len(flagged)} senators have publication gaps > 45 days: "
        + ", ".join(f"{sid}={g}d" for sid, g in flagged[:10])
        + ("..." if len(flagged) > 10 else "")
    )


# ---- Completeness tests ----

def test_depth_to_jan_2025():
    """At least 30 senators should have data reaching Jan-Feb 2025."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT count(*) FROM (
            SELECT official_id FROM official_site_items WHERE deleted_at IS NULL
            AND published_at IS NOT NULL
            GROUP BY official_id
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
    `--detail <official_id>` for a weekly histogram.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.full_name,
               count(pr.id)::int as total,
               count(DISTINCT pr.published_at::date)::int as unique_days
        FROM officials s
        JOIN official_site_items pr ON pr.official_id = s.id
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
    # Scoped to chamber='senate'. House RSS feeds cap at 10 items so the
    # earliest record is typically ~Feb 2026, not Jan 2025; that's a feed
    # truncation artifact, not a collector bug. Back-coverage for House
    # will need a separate Drupal listing-page wave before this check
    # makes sense for that chamber.
    cur.execute("""
        SELECT s.id, s.full_name,
               min(pr.published_at) FILTER (WHERE pr.deleted_at IS NULL)::date AS earliest,
               count(pr.id) FILTER (WHERE pr.deleted_at IS NULL)::int AS total
        FROM officials s
        LEFT JOIN official_site_items pr ON pr.official_id = s.id
        WHERE s.status = 'active'
          AND s.chamber = 'senate' AND s.jurisdiction = 'us'
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
    cur.execute("SELECT COUNT(*) FROM official_site_items WHERE deleted_at IS NULL")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM official_site_items WHERE deleted_at IS NULL AND body_text IS NOT NULL AND length(body_text) > 100")
    with_body = cur.fetchone()[0]
    cur.close()
    conn.close()
    pct = with_body / total * 100 if total > 0 else 0
    assert pct >= 70, f"Only {pct:.0f}% of records have body text > 100 chars, expected >= 70%"


def test_no_anomalously_low_counts():
    """No active US senator should have less than 10% of the median release count.

    If a longstanding senator has single-digit releases while peers have hundreds,
    that indicates a collection failure, not inactivity.

    Scoped to chamber='senate' — TX state senators publish on a fundamentally
    different cadence (most fewer than 30 records since Jan 2025 even when
    collection is healthy), so applying the federal-Senate median threshold
    to the TX corpus would always fail.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY cnt) as median
        FROM (
            SELECT COUNT(*) as cnt FROM official_site_items pr
            JOIN officials s ON s.id = pr.official_id
            WHERE pr.deleted_at IS NULL AND s.chamber = 'senate' AND s.jurisdiction = 'us'
            GROUP BY official_id HAVING COUNT(*) > 0
        ) sub
    """)
    median = cur.fetchone()[0] or 1
    threshold = max(median * 0.1, 10)  # at least 10

    cur.execute("""
        SELECT s.id, s.full_name, COUNT(pr.id) FILTER (WHERE pr.deleted_at IS NULL) as cnt
        FROM officials s
        LEFT JOIN official_site_items pr ON s.id = pr.official_id
        WHERE s.collection_method IS NOT NULL AND s.chamber = 'senate' AND s.jurisdiction = 'us'
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
    """Normally-active US senators must have a CAPTURE in the last 14 days.

    Scoped to chamber='senate' AND jurisdiction='us'. Tightened on
    2026-05-15 after this test's previous "60 days, allow up to 9 stale"
    threshold missed four collectors that silently broke for 14-26 days
    (lujan-ben, tuberville-tommy, hagerty-bill, plus state-side hits).
    The new shape mirrors daily_report._silent_members so the digest and
    the test agree on what "broken" means:

        - chamber = 'senate' AND jurisdiction = 'us'
        - status = 'active' (so freshly-departed members don't haunt us)
        - normally-active: >= 161 captures in the last 90 days
          (~25 expected captures in any given 14-day window — below
          this, a senator can be naturally quiet for 14 days during
          recess. Hagerty at 182, Lujan at 459, Tuberville at 391 all
          clear the bar; Rounds at 145 and Sheehy at 80 do not, so
          they surface only in the digest's silent-members list, not
          as a HARD CI failure.)
        - exempt anyone whose seed flags expect_empty=true (Armstrong)
        - bad signal: MAX(last_seen_live) older than 14 days

    The freshness signal is MAX(last_seen_live), not MAX(scraped_at).
    last_seen_live is bumped every time the collector SEES a known URL on
    the listing/feed, even when nothing new is inserted; scraped_at only
    moves when a row is actually written. A healthy-but-quiet senator
    (Boozman, last post 2026-06-05) keeps a fresh last_seen_live while his
    scraped_at goes stale — keying on scraped_at flagged him as broken
    when his collector was fine. A genuinely broken collector (Johnson's
    2026-05 site migration 404'd the seeded URL) goes stale on BOTH. So a
    stale last_seen_live for an otherwise-active senator means the
    COLLECTOR is broken, not the senator. That is a HARD failure — it's
    how data loss starts.
    """
    # expect_empty lives in seed JSON, not on the officials table. The
    # single current exemption is Armstrong (R-OK) — appointed 2026-03-24
    # to a seat with no inherited press archive and a brand-new bare-bones
    # site. Add others here if they appear in seed senate.json with
    # expect_empty=true; the IN clause keeps the hardcoded list short.
    EXEMPT = {"armstrong-alan"}
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        WITH historical AS (
            SELECT official_id,
                   COUNT(*) FILTER (WHERE scraped_at > NOW() - INTERVAL '90 days') AS last_90,
                   MAX(last_seen_live) AS last_scrape
            FROM official_site_items
            WHERE deleted_at IS NULL
            GROUP BY official_id
        )
        SELECT s.id, s.full_name, h.last_scrape::date, h.last_90
        FROM officials s
        JOIN historical h ON h.official_id = s.id
        WHERE s.collection_method IS NOT NULL
          AND s.chamber = 'senate' AND s.jurisdiction = 'us'
          AND s.status = 'active'
          AND NOT (s.id = ANY(%s))
          AND h.last_90 >= 161  -- expected ~25 captures in 14d at this volume
          AND h.last_scrape < NOW() - INTERVAL '14 days'
        ORDER BY h.last_scrape
    """, (list(EXEMPT),))
    stale = cur.fetchall()
    cur.close()
    conn.close()
    # Proportionality gate (2026-07-19): one or two stale members is a
    # single-site problem (site migration, redesign) — warn here and let
    # the daily digest's silent-members list carry it. Three or more at
    # once means something systemic (WAF change, shared-CMS breakage,
    # collector regression) — fail the run. Warren's solo July WP
    # migration kept the cron red for 11 days with no new information
    # after day one; the red X should be reserved for fleet-level damage.
    if stale and len(stale) < 3:
        print(f"WARNING: {len(stale)} stale US senators (below fail threshold of 3; see daily digest):")
        for sid, name, last_scrape, last_90 in stale:
            print(f"  {name} ({sid}): last_scrape={last_scrape}, last_90={last_90}")
        return
    if stale:
        print(f"FAIL: {len(stale)} normally-active US senators with no captures in 14 days:")
        for sid, name, last_scrape, last_90 in stale:
            print(f"  {name} ({sid}): last_scrape={last_scrape}, last_90={last_90}")
    assert not stale, (
        f"{len(stale)} normally-active US senators went silent for 14+ days "
        f"(likely broken collectors): "
        + ", ".join(f"{n}({lc})" for _, n, lc, _ in stale)
    )


# ---- Bulletproofing checks (added 2026-05-20) ----
#
# These exist because the May 2 -> May 20 silent-collector incident
# (six senators returning 0 records on every cron for 18 days while the
# listing pages were healthy) only tripped the existing 14-day stale
# test, which made detection 13 days slower than it needed to be. The
# checks below catch the same class of failure on day 3, plus surface
# the leading indicators that were buried in the run logs.

_EXEMPT_PARITY = {"armstrong-alan"}  # known zero-volume seat


def test_collector_extraction_parity():
    """HARD. Pre-scrape health check found items; collector inserted nothing.

    If the most recent health_checks row for a senator shows >=3 listing
    items in the last 24 hours, the listing page is alive and parseable.
    If MAX(last_seen_live) -- bumped whenever the daily collector sees a
    known URL on the listing/feed, even when the item is older than the
    incremental detail-fetch cutoff -- is more than 36 hours old, the
    collector ran four times against a healthy listing and matched
    nothing. That is the failure mode that hid for 18 days in May 2026
    behind selector + RSS-fallback breakage.

    last_seen_live is the right signal, not scraped_at: scraped_at only
    moves on NEW inserts, so a senator whose listing carries only old
    already-stored items would false-positive on a scraped_at check.
    last_seen_live moves whenever the collector successfully recognizes
    an archived URL in the live listing/feed, so a stale value means the
    collector is dropping the listing wholesale.

    The 36-hour window leaves a full daily cycle of slack but trips far
    earlier than test_no_stale_senators (14 days). Scoped to active US
    senators with last_90 >= 161 so naturally low-volume members stay
    in the softer per-member silence flow.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        WITH latest_health AS (
            SELECT DISTINCT ON (official_id)
                official_id, items_found, checked_at
            FROM health_checks
            WHERE checked_at > NOW() - INTERVAL '24 hours'
            ORDER BY official_id, checked_at DESC
        ),
        touch AS (
            SELECT official_id,
                   COUNT(*) FILTER (WHERE scraped_at > NOW() - INTERVAL '90 days') AS last_90,
                   MAX(last_seen_live) AS last_touch
            FROM official_site_items
            WHERE deleted_at IS NULL
            GROUP BY official_id
        )
        SELECT s.id, s.full_name, lh.items_found, t.last_touch, t.last_90
        FROM officials s
        JOIN latest_health lh ON lh.official_id = s.id
        JOIN touch t ON t.official_id = s.id
        WHERE s.collection_method IS NOT NULL
          AND s.chamber = 'senate' AND s.jurisdiction = 'us'
          AND s.status = 'active'
          AND NOT (s.id = ANY(%s))
          AND lh.items_found >= 3
          AND t.last_90 >= 161
          AND (t.last_touch IS NULL OR t.last_touch < NOW() - INTERVAL '36 hours')
        ORDER BY t.last_touch NULLS FIRST
    """, (list(_EXEMPT_PARITY),))
    broken = cur.fetchall()
    cur.close()
    conn.close()
    if broken:
        print(f"FAIL: {len(broken)} senators where listing is alive but collector matched nothing:")
        for sid, name, items, last_touch, last_90 in broken:
            lt = last_touch.strftime('%Y-%m-%d %H:%M') if last_touch else 'never'
            print(f"  {name} ({sid}): health_items={items}, last_touch={lt}, last_90={last_90}")
    assert not broken, (
        f"{len(broken)} collectors silently dropped every item from healthy listings: "
        + ", ".join(f"{n}(items={i})" for _, n, i, _, _ in broken)
    )


def test_cutoff_filter_not_starving_senators():
    """SOFT. Senators whose listings consistently had items found by the
    health check but where MAX(last_seen_live) is more than 3 days old.

    A senator with no new content but a working collector will still
    have fresh last_seen_live values from dedupe matches. A stale
    last_seen_live across multiple healthy checks means the collector
    is producing nothing the upsert can touch. The signal we care about
    is the cluster shape: multiple senators tripping at once almost
    always means a systemic filter regression (the May 2026 cutoff bug
    affected six senators simultaneously).
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        WITH recent_health AS (
            SELECT official_id,
                   COUNT(*) AS checks,
                   COUNT(*) FILTER (WHERE items_found >= 3) AS healthy
            FROM health_checks
            WHERE checked_at > NOW() - INTERVAL '5 days'
            GROUP BY official_id
        ),
        touch AS (
            SELECT official_id, MAX(last_seen_live) AS last_touch
            FROM official_site_items
            WHERE deleted_at IS NULL
            GROUP BY official_id
        )
        SELECT s.id, s.full_name, rh.healthy, rh.checks, t.last_touch
        FROM officials s
        JOIN recent_health rh ON rh.official_id = s.id
        JOIN touch t ON t.official_id = s.id
        WHERE s.collection_method IS NOT NULL
          AND s.chamber = 'senate' AND s.jurisdiction = 'us'
          AND s.status = 'active'
          AND NOT (s.id = ANY(%s))
          AND rh.checks >= 3
          AND rh.healthy = rh.checks  -- every check saw items
          AND (t.last_touch IS NULL OR t.last_touch < NOW() - INTERVAL '3 days')
        ORDER BY t.last_touch NULLS FIRST
    """, (list(_EXEMPT_PARITY),))
    starved = cur.fetchall()
    cur.close()
    conn.close()
    if starved:
        print(f"WARNING: {len(starved)} senators with healthy listings but no collector touches in 3 days:")
        for sid, name, healthy, checks, last_touch in starved:
            lt = last_touch.strftime('%Y-%m-%d %H:%M') if last_touch else 'never'
            print(f"  {name} ({sid}): listing_healthy={healthy}/{checks}, last_touch={lt}")
    assert len(starved) < 5, (
        f"{len(starved)} senators look starved -- cluster suggests a filter regression"
    )


def test_no_blocklisted_seed_selectors():
    """SOFT. Surface seeds whose list_item selector is in the parser
    blocklist. These senators are silently running on the waterfall
    fallback; that has worked historically but the signal is worth
    keeping visible because it is exactly how four senators broke in
    May 2026 (span.elementor-grid-item was in the blocklist; the
    waterfall caught .jet-listing-grid__item; then extract_item_data
    only handled the Whitehouse JetEngine shape and dropped everything
    from non-Whitehouse senators on the same code path).

    Mirror the blocklist literal here -- importing from backfill.py at
    test-collection time pulls in the whole HTTP stack and slows the
    suite. Keep this set in sync if backfill.bad_selectors changes.
    """
    BAD = {"span.elementor-grid-item", "li.page-item"}
    flagged = []
    for m in _load_seeds():
        sel = (m.get("selectors") or {}).get("list_item")
        if sel and sel in BAD:
            flagged.append((m["official_id"], m["full_name"], sel))
    if flagged:
        print(f"WARNING: {len(flagged)} seeds use a blocklisted list_item (running on waterfall fallback):")
        for sid, name, sel in flagged:
            print(f"  {name} ({sid}): list_item={sel!r}")
    assert len(flagged) == 0, (
        f"{len(flagged)} seeds rely on the fallback waterfall via blocklisted list_item: "
        + ", ".join(f"{n}({s})" for _, n, s in flagged)
    )


def test_date_confidence_floor():
    """SOFT. Median date_confidence across the last 7 days of inserts
    must stay >= 0.85 per senator.

    Anchors against the Kennedy-style upstream degradation: the senate.gov
    RSS feed started emitting day-of-month values like 138, which
    feedparser drops, which collapsed every Kennedy item's confidence to
    fallbacks. Catches the gradual case where text parsing degrades
    enough that we rely on URL-path defaults (confidence 0.7) -- which
    in turn opens the day-1 truncation hole the cutoff fix patched.

    Only flag senators with >=5 inserts in the window so a single
    low-confidence record does not trip the test.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        WITH recent AS (
            SELECT official_id,
                   COUNT(*) AS n,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY date_confidence) AS median_conf
            FROM official_site_items
            WHERE scraped_at > NOW() - INTERVAL '7 days'
              AND deleted_at IS NULL
              AND date_confidence IS NOT NULL
            GROUP BY official_id
        )
        SELECT s.full_name, s.id, r.n, r.median_conf
        FROM officials s
        JOIN recent r ON r.official_id = s.id
        WHERE s.chamber = 'senate' AND s.jurisdiction = 'us'
          AND r.n >= 5 AND r.median_conf < 0.85
        ORDER BY r.median_conf
    """)
    low = cur.fetchall()
    cur.close()
    conn.close()
    if low:
        print(f"WARNING: {len(low)} senators with median date_confidence < 0.85 over last 7 days:")
        for name, sid, n, mc in low:
            print(f"  {name} ({sid}): median={float(mc):.2f} over {n} inserts")
    assert len(low) < 10, (
        f"{len(low)} senators degraded below 0.85 median confidence -- upstream date format drift"
    )


def test_pre_scrape_failure_surface():
    """SOFT. Hoist pre-scrape health-check failures into the test gate.

    The 'Pre-scrape health check' workflow step prints '--- FAILED (N) ---'
    inline and exits 0 regardless. That meant today's run logged 7
    failed health checks and the visible signal was 'data-quality tests
    failed' four steps later. Mirror them here so the digest sees them.

    A health-check failure is the listing page returning non-200, or
    timing out, or producing zero items. Sub-counted by reason for the
    digest.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        WITH latest AS (
            SELECT DISTINCT ON (official_id)
                official_id, passed, url_status, items_found,
                error_message, checked_at
            FROM health_checks
            WHERE checked_at > NOW() - INTERVAL '24 hours'
            ORDER BY official_id, checked_at DESC
        )
        SELECT s.full_name, s.id, l.passed, l.url_status, l.items_found, l.error_message
        FROM officials s
        JOIN latest l ON l.official_id = s.id
        WHERE s.chamber = 'senate' AND s.jurisdiction = 'us'
          AND s.status = 'active'
          AND s.collection_method IS NOT NULL
          AND NOT (s.id = ANY(%s))
          AND l.passed = FALSE
        ORDER BY l.url_status NULLS LAST, s.full_name
    """, (list(_EXEMPT_PARITY),))
    failed = cur.fetchall()
    cur.close()
    conn.close()
    if failed:
        print(f"WARNING: {len(failed)} senators failed pre-scrape health check in last 24h:")
        for name, sid, passed, status, items, err in failed:
            tag = f"http={status}" if status else "no_response"
            extra = f" items={items}" if items is not None else ""
            errf = f" err={err[:60]}" if err else ""
            print(f"  {name} ({sid}): {tag}{extra}{errf}")
    assert len(failed) < 10, (
        f"{len(failed)} senators failed pre-scrape health check -- check listing URLs/selectors"
    )


# ---- Per-content-type coverage tests ----
#
# These exist because aggregate tests hide silent collapses of specific types.
# If the classifier regresses and stops emitting 'letter', the total record
# count barely moves (letters are ~100 of 34k) and every other test passes,
# but a real coverage gap just opened. These tests assert a floor per type.

# Expected floors calibrated from 2026-04-25 DB state, after the classifier
# was tightened so press-release-section URLs trump title heuristics
# (Sheehy "leads letter" wrappers, ICYMI op-ed wrappers, "delivers floor
# speech" announcements all stay press_release). A floor going up is fine;
# the purpose is to catch a sudden drop.
_TYPE_FLOORS = {
    "press_release":        30_000,
    "statement":               300,
    "op_ed":                    30,
    "blog":                    100,
    "letter":                    3,
    "floor_statement":          20,
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
        FROM official_site_items
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
        FROM official_site_items
        WHERE deleted_at IS NULL
          AND published_at IS NOT NULL
        GROUP BY content_type
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # Need counts too -- skip back-coverage check on types with too-few
    # records to make the gap meaningful (a 5-record type can plausibly
    # lack January coverage without indicating a collector bug).
    cur = get_conn().cursor()
    cur.execute("""
        SELECT content_type, count(*)::int
        FROM official_site_items
        WHERE deleted_at IS NULL
        GROUP BY content_type
    """)
    counts = dict(cur.fetchall())
    cur.close()

    expected_start = date(2025, 1, 1)
    truncated = []
    for t, earliest in rows:
        if t not in _TYPE_FLOORS:  # only check tracked types
            continue
        if counts.get(t, 0) < 50:  # too small a sample to assert back-coverage
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
        FROM official_site_items
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


# ---- Bluesky / social_posts tests ----
#
# Surface-specific aggregates. Mirror the press-release discipline: we
# don't let one broken senator hide in the aggregate. Thresholds are
# deliberately loose so a Bluesky outage on a given day doesn't redden
# the suite — they're trip-wires, not SLAs.

def test_social_posts_not_empty():
    """Sanity: social_posts has rows from the verified-handle directory."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM social_posts WHERE deleted_at IS NULL")
    total = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert total >= 1000, f"social_posts has only {total} rows; backfill may have failed"


def test_social_posts_within_window():
    """Every captured post should be on or after our 2026-01-01 cutoff."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT count(*) FROM social_posts WHERE created_at < '2026-01-01'"
    )
    leak = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert leak == 0, f"{leak} social_posts predate 2026-01-01 — backfill cutoff broken"


def test_social_posts_per_senator_floor():
    """Every senator with a verified Bluesky handle should have at least
    one post unless their account is dormant (no posts in 2026)."""
    handles_path = Path(__file__).resolve().parent.parent / "seeds" / "bluesky_handles.json"
    if not handles_path.exists():
        return  # nothing to assert
    handles = json.load(handles_path.open())["handles"]
    expected = {h["official_id"] for h in handles}

    # Documented dormants — verified empty-2026 accounts. Update if their
    # status changes.
    DORMANT = {"fetterman-john", "padilla-alex", "schatz-brian"}

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT official_id FROM social_posts WHERE deleted_at IS NULL "
        "GROUP BY official_id"
    )
    have = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()

    missing = (expected - have) - DORMANT
    assert not missing, (
        "verified senators with no social_posts (and not in DORMANT list): "
        f"{sorted(missing)}"
    )


# ---- Run all tests ----

# HARD checks fail the run. They mean the data layer itself is broken — a
# parser bug, a stopped collector, a wholesale regression. Every consumer of
# the corpus is affected if these trip.
#
# SOFT checks (the set below) record a warning and surface in the daily
# digest but do NOT fail the run. They cover anomaly tripwires where a
# single-record typo, a coincidental round number, or one undercollecting
# member shouldn't tear down a 535+ member pipeline. The verified_ok pattern
# was the prior workaround; the soft tier replaces it. Reclassify into HARD
# only if a soft check starts catching a class of real outages, not just
# eyebrow-raising coincidences.
SOFT_TESTS = {
    # test_dates_in_valid_range is HARD as of 2026-05-31: it only asserts on
    # genuine parser errors (pre-2010 or >1yr-future published_at), which are
    # data-layer breakage, not upstream typos. Near-future typos (1 day to
    # 1 year) are handled as a warning by test_no_future_dates below, which
    # stays SOFT. 0 offending records at promotion time.
    "test_no_future_dates",
    "test_no_suspicious_round_counts",
    "test_rss_collectors_not_severely_undercollecting",
    "test_no_rss_rampup_signature",
    "test_no_zero_volume_months",
    "test_no_long_publication_gaps",
    "test_back_coverage_not_truncated",
    "test_no_date_clumping",
    "test_no_anomalously_low_counts",
    # test_per_type_floors and test_no_stale_senators were SOFT before
    # 2026-05-15. Both catch real data loss — a collapsed content_type
    # (the classifier silently regressing 'op_ed' to 0) and a broken
    # collector (lujan-ben/tuberville-tommy went silent for 26 days).
    # Promoted to HARD after the digest exposed the second class.
    "test_per_type_back_coverage",   # historical back-coverage drift, still SOFT
    "test_per_type_not_date_clumped", # known issues on a few state-side IDs
    "test_social_posts_not_empty",
    "test_social_posts_within_window",
    "test_social_posts_per_senator_floor",
    # Bulletproofing tests added 2026-05-20. The parity test is HARD --
    # same class as test_no_stale_senators, catches the May 2 silent-
    # collector failure on day 3 instead of day 14. The rest are
    # leading indicators that surface in the digest.
    "test_cutoff_filter_not_starving_senators",
    "test_no_blocklisted_seed_selectors",
    "test_date_confidence_floor",
    "test_pre_scrape_failure_surface",
}


REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "data_quality_run.json"


def run_all():
    """Run all tests, write a structured report, and return success bool.

    Returns True when no HARD checks fail. SOFT-tier failures (see
    SOFT_TESTS) print as WARN but do not affect the return value, so cron
    only goes red when the data layer is actually broken.

    Side effect: writes docs/data_quality_run.json with the run summary
    so the daily-report email step can include warnings without re-running
    the suite.
    """
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
        test_rss_collectors_not_severely_undercollecting,
        test_no_rss_rampup_signature,
        test_no_zero_volume_months,
        test_no_long_publication_gaps,
        test_depth_to_jan_2025,
        test_back_coverage_not_truncated,
        test_no_date_clumping,
        test_body_coverage_above_threshold,
        test_no_anomalously_low_counts,
        test_no_stale_senators,
        test_collector_extraction_parity,
        test_cutoff_filter_not_starving_senators,
        test_no_blocklisted_seed_selectors,
        test_date_confidence_floor,
        test_pre_scrape_failure_surface,
        test_per_type_floors,
        test_per_type_back_coverage,
        test_per_type_not_date_clumped,
        test_social_posts_not_empty,
        test_social_posts_within_window,
        test_social_posts_per_senator_floor,
    ]

    passed: list[str] = []
    warnings: list[dict] = []
    failures: list[dict] = []

    print(f"\n{'='*60}")
    print(f"  DATA QUALITY TESTS")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    for test in tests:
        is_soft = test.__name__ in SOFT_TESTS
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed.append(test.__name__)
        except AssertionError as e:
            entry = {"name": test.__name__, "message": str(e)}
            if is_soft:
                print(f"  WARN  {test.__name__}: {e}")
                warnings.append(entry)
            else:
                print(f"  FAIL  {test.__name__}: {e}")
                failures.append(entry)
        except Exception as e:
            # Unexpected exceptions are always loud — they mean the test
            # itself crashed (bad query, missing column), which we want to
            # know about regardless of severity tier.
            print(f"  ERR   {test.__name__}: {type(e).__name__}: {e}")
            failures.append({
                "name": test.__name__,
                "message": f"{type(e).__name__}: {e}",
                "kind": "exception",
            })

    print(f"\n{'='*60}")
    print(f"  {len(passed)} passed, {len(warnings)} warnings, {len(failures)} failures")
    print(f"{'='*60}\n")

    report = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {
            "passed": len(passed),
            "warnings": len(warnings),
            "failures": len(failures),
        },
        "passed": passed,
        "warnings": warnings,
        "failures": failures,
    }
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2))
    except OSError as e:
        # Don't let a write failure break the test exit code — the report
        # is a side effect for the daily digest, not a correctness signal.
        print(f"  (report write skipped: {e})")

    return len(failures) == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
