"""Compare the federal and state tiers on the same quality dimensions.

The state expansion is only credible if state data is held to the standard
the Senate corpus set. This prints both tiers side by side so the claim can
be checked rather than asserted.

Scale is deliberately NOT a dimension here. The federal tier has an order
of magnitude more records simply because it has more officials and a longer
head start; that says nothing about whether either tier is trustworthy. The
dimensions below are all ratios or provenance measures, so a 7k-record tier
and a 94k-record tier can be compared honestly.

"Undocumented empty" counts sources that collect nothing AND carry no
`expect_empty` reason. The distinction is the whole point: counting empty
sources without it reported every deliberately-empty office as a gap and
made the state tier look 8.3% broken when all 13 of its empty sources
were documented and verified. That flag became a column in migration 019
so this can be a single query.

Usage:
    python -m pipeline tiers
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv(".env.local")


def _connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    return psycopg2.connect(url)


def _fmt(v, suffix=""):
    return "—" if v is None else f"{v}{suffix}"


def main():
    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT CASE WHEN o.jurisdiction = 'us' THEN 'federal' ELSE 'state' END AS tier,
               COUNT(DISTINCT o.id) FILTER (WHERE o.collection_method IS NOT NULL) AS sources,
               COUNT(i.id) AS records,
               ROUND(100.0 * COUNT(i.published_at) / NULLIF(COUNT(i.id), 0), 1) AS pct_dated,
               ROUND(AVG(i.date_confidence)::numeric, 2) AS avg_conf,
               ROUND(100.0 * COUNT(i.body_text) / NULLIF(COUNT(i.id), 0), 1) AS pct_body,
               MIN(i.published_at)::date AS oldest,
               COUNT(DISTINCT i.date_source) AS date_sources
        FROM officials o
        LEFT JOIN official_site_items i
          ON i.official_id = o.id AND i.deleted_at IS NULL
        WHERE o.status = 'active'
        GROUP BY 1
        """
    )
    stats = {r[0]: r for r in cur.fetchall()}

    cur.execute(
        """
        SELECT CASE WHEN o.jurisdiction = 'us' THEN 'federal' ELSE 'state' END,
               o.id
        FROM officials o
        WHERE o.status = 'active'
          AND o.collection_method IS NOT NULL
          AND NOT o.expect_empty
          AND NOT EXISTS (
            SELECT 1 FROM official_site_items i
            WHERE i.official_id = o.id AND i.deleted_at IS NULL
          )
        """
    )
    gaps = {"federal": [], "state": []}
    for tier, sid in cur.fetchall():
        gaps[tier].append(sid)
    cur.close()
    conn.close()

    rows = [
        ("Collecting sources", lambda s: _fmt(s[1])),
        ("Records", lambda s: f"{s[2]:,}"),
        ("Dated", lambda s: _fmt(s[3], "%")),
        ("Mean date confidence", lambda s: _fmt(s[4])),
        ("With body text", lambda s: _fmt(s[5], "%")),
        ("Archive reaches back to", lambda s: _fmt(s[6])),
        ("Distinct date sources", lambda s: _fmt(s[7])),
    ]

    print("\n" + "=" * 62)
    print("  TIER COMPARISON — federal vs state")
    print("=" * 62)
    print(f"  {'':26} {'FEDERAL':>14} {'STATE':>14}")
    for label, fn in rows:
        f = fn(stats["federal"]) if "federal" in stats else "—"
        s = fn(stats["state"]) if "state" in stats else "—"
        print(f"  {label:26} {f:>14} {s:>14}")

    print(f"  {'Undocumented empty sources':26} "
          f"{len(gaps['federal']):>14} {len(gaps['state']):>14}")
    print("=" * 62)

    for tier in ("federal", "state"):
        if gaps[tier]:
            print(f"  {tier} sources empty with no expect_empty reason:")
            for sid in sorted(gaps[tier])[:10]:
                print(f"    - {sid}")
    print()


if __name__ == "__main__":
    main()
