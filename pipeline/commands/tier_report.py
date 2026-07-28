"""Compare the federal and state tiers on the same quality dimensions.

The state expansion is only credible if state data is held to the standard
the Senate corpus set. This prints both tiers side by side so the claim can
be checked rather than asserted.

Scale is deliberately NOT a dimension here. The federal tier has an order
of magnitude more records simply because it has more officials and a longer
head start; that says nothing about whether either tier is trustworthy. The
dimensions below are all ratios or provenance measures, so a 7k-record tier
and a 94k-record tier can be compared honestly.

One measure has to come from the seeds rather than SQL: `expect_empty`
lives in the seed JSON and was never synced to a database column. That
matters more than it sounds. Counting empty sources straight from the
database reports every deliberately-empty office as a gap -- on 2026-07-28
that made the state tier look 8.3% broken when every one of its 13 empty
sources was documented and verified.

Usage:
    python -m pipeline tiers
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

from pipeline.lib.seeds import load_members

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
        SELECT o.id FROM officials o
        WHERE o.status = 'active' AND o.collection_method IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM official_site_items i
            WHERE i.official_id = o.id AND i.deleted_at IS NULL
          )
        """
    )
    empty_ids = {r[0] for r in cur.fetchall()}
    cur.close()
    conn.close()

    seeds = {m["official_id"]: m for m in load_members(include_unconfigured=True)}
    gaps = {"federal": [], "state": []}
    for sid in empty_ids:
        seed = seeds.get(sid, {})
        tier = "federal" if seed.get("jurisdiction") == "us" else "state"
        if not seed.get("expect_empty"):
            gaps[tier].append(sid)

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
