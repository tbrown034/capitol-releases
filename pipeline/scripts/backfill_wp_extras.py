"""Bulk-collect untapped WP custom post types per senator.

Some senators publish original content under post types our seed config
never sees: /wp/v2/newsletters, /wp/v2/bernie-buzz, /wp/v2/speeches, etc.
This script walks those endpoints and inserts records with the right
content_type per the EXTRAS map below.

Usage:
    python -m pipeline.scripts.backfill_wp_extras
    python -m pipeline.scripts.backfill_wp_extras --senator young-todd
    python -m pipeline.scripts.backfill_wp_extras --dry-run

Each (senator, post_type) pair maps to a content_type. Add new pairs
as audits surface them.
"""
import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg2
from bs4 import BeautifulSoup

from pipeline.backfill_wp_json import fetch_all, html_to_text, load_env, normalize_url

CUTOFF = date(2025, 1, 1)

# (senator_id, wp_post_type) -> content_type
EXTRAS: dict[tuple[str, str], str] = {
    ("rochester-lisa", "newsletter"): "blog",
    ("young-todd", "newsletter"): "blog",
    ("scott-tim", "newsletter"): "blog",
    ("scott-tim", "sweet_tea"): "blog",
    ("husted-jon", "newsletters"): "blog",
    ("curtis-john", "newsletters"): "blog",
    ("sanders-bernard", "bernie-buzz"): "blog",
    ("whitehouse-sheldon", "blogs"): "blog",
    ("whitehouse-sheldon", "speeches"): "floor_statement",
    ("mccormick-david", "remarks"): "floor_statement",
    ("lankford-james", "newsletter"): "blog",
    ("risch-james", "newsletter"): "blog",
    ("masto-catherine", "newsletter"): "blog",
    ("padilla-alex", "newsletter"): "blog",
    # Discovered 2026-04-27 in content_stream recon (162 records waiting).
    ("ricketts-pete", "weekly_column"): "blog",
}


def collect_for(
    conn, senator_id: str, post_type: str, content_type: str, base_url: str, dry_run: bool
) -> dict:
    print(f"\n[{senator_id}] /wp/v2/{post_type} -> {content_type}")
    records = fetch_all(
        base_url, post_type, extra_params={"after": "2025-01-01T00:00:00"}
    )
    print(f"  fetched {len(records)} in-window records")

    run_id = f"wpx-{senator_id}-{post_type}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    if not dry_run:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO scrape_runs (id, run_type) VALUES (%s, 'backfill')", (run_id,)
        )
        conn.commit()
        cur.close()

    counts = {"inserted": 0, "skipped_existing": 0, "skipped_pre_cutoff": 0, "skipped_short": 0}

    for rec in records:
        link = rec.get("link")
        if not link:
            continue
        source_url = normalize_url(link)
        date_str = rec.get("date_gmt") or rec.get("date")
        if not date_str:
            continue
        try:
            pub_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        if pub_dt.date() < CUTOFF:
            counts["skipped_pre_cutoff"] += 1
            continue

        title_raw = rec.get("title", {})
        title = title_raw.get("rendered") if isinstance(title_raw, dict) else (title_raw or "")
        title = BeautifulSoup(title or "", "lxml").get_text(strip=True)
        if len(title) < 5:
            counts["skipped_short"] += 1
            continue

        content_raw = rec.get("content", {})
        content_html = content_raw.get("rendered") if isinstance(content_raw, dict) else ""
        body_text = html_to_text(content_html)

        if dry_run:
            print(f"    {pub_dt.date()} | {title[:80]}")
            continue

        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO press_releases
                  (senator_id, title, published_at, body_text, source_url,
                   scrape_run, content_type, date_source, date_confidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'wp_json', 1.0)
                ON CONFLICT (source_url) DO NOTHING
                """,
                (senator_id, title, pub_dt, body_text or None, source_url, run_id, content_type),
            )
            conn.commit()
            if cur.rowcount > 0:
                counts["inserted"] += 1
            else:
                counts["skipped_existing"] += 1
        except Exception as e:
            conn.rollback()
            print(f"    ERR on {source_url}: {e}")
        finally:
            cur.close()

    if not dry_run:
        cur = conn.cursor()
        cur.execute(
            "UPDATE scrape_runs SET finished_at = NOW(), stats = %s::jsonb WHERE id = %s",
            (json.dumps(counts), run_id),
        )
        conn.commit()
        cur.close()

    print(f"  result: {counts}")
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--senator", help="Run only for one senator_id")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env()
    seeds = json.load(
        open(Path(__file__).resolve().parents[1] / "seeds" / "senate.json")
    )["members"]
    base_by_id = {s["senator_id"]: (s.get("official_url") or "").rstrip("/") for s in seeds}

    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    pairs = [(sid, pt, ct) for (sid, pt), ct in EXTRAS.items()]
    if args.senator:
        pairs = [p for p in pairs if p[0] == args.senator]

    grand = {"inserted": 0, "skipped_existing": 0, "skipped_pre_cutoff": 0, "skipped_short": 0}
    for sid, pt, ct in pairs:
        base = base_by_id.get(sid)
        if not base:
            print(f"[{sid}] no official_url in seed -- skipping")
            continue
        c = collect_for(conn, sid, pt, ct, base, args.dry_run)
        for k in grand:
            grand[k] += c[k]

    print(f"\nGRAND TOTAL: {grand}")
    conn.close()


if __name__ == "__main__":
    main()
