"""Bulk-collect op-eds from any senator whose WP site exposes /wp/v2/op_eds.

12 senators (as of 2026-04-25) publish op-eds under a custom WP post type
that's invisible to our /press-releases/-targeted seed config. This script
walks their WP-JSON and inserts records with content_type='op_ed'.

Usage:
    python -m pipeline.scripts.backfill_op_eds              # all senators
    python -m pipeline.scripts.backfill_op_eds --senator coons-christopher
    python -m pipeline.scripts.backfill_op_eds --dry-run

Paul-specific quirk: a 2026-03-02 migration re-stamped the dates of his
recent op-eds. Detected by date-prefix + (modified - date) < 120s, those
records are flagged date_source='wp_modified_migration' confidence=0.3.
Numbered-slug duplicates (-2/-3) are skipped when stamped.
"""
import argparse
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import psycopg2
from bs4 import BeautifulSoup

from pipeline.backfill_wp_json import fetch_all, html_to_text, load_env, normalize_url

CUTOFF = date(2025, 1, 1)
NUMBERED_SUFFIX = re.compile(r"-\d+$")

# Per-senator migration windows; extend if other senators show the same pattern.
MIGRATION_WINDOWS: dict[str, str] = {
    "paul-rand": "2026-03-02",
    "hagerty-bill": "2025-09-29",
}


def candidate_senators() -> list[dict]:
    """Senators with op_eds on WP-JSON. Probe their /wp/v2/op_eds?per_page=1."""
    seeds = json.load(
        open(Path(__file__).resolve().parents[1] / "seeds" / "senate.json")
    )["members"]
    hits: list[dict] = []
    with httpx.Client(timeout=10, follow_redirects=True) as client:
        for s in seeds:
            base = (s.get("official_url") or "").rstrip("/")
            if not base:
                continue
            try:
                r = client.get(f"{base}/wp-json/wp/v2/op_eds?per_page=1")
                if r.status_code != 200:
                    continue
                data = r.json()
                if not isinstance(data, list):
                    continue
                total = int(r.headers.get("x-wp-total", "0") or 0)
                if total > 0:
                    hits.append({"senator_id": s["senator_id"], "base": base, "total": total})
            except Exception:
                continue
    return hits


def is_migration_stamped(rec: dict, prefix: str) -> bool:
    date_iso = rec.get("date_gmt") or rec.get("date") or ""
    mod_iso = rec.get("modified_gmt") or rec.get("modified") or ""
    if not date_iso.startswith(prefix):
        return False
    try:
        d = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
        m = datetime.fromisoformat(mod_iso.replace("Z", "+00:00"))
    except ValueError:
        return True
    return abs((m - d).total_seconds()) < 120


def collect_for(conn, senator_id: str, base_url: str, dry_run: bool) -> dict:
    migration_prefix = MIGRATION_WINDOWS.get(senator_id)
    print(f"\n[{senator_id}] fetching op-eds from {base_url}")
    records = fetch_all(
        base_url, "op_eds", extra_params={"after": "2025-01-01T00:00:00"}
    )
    print(f"  fetched {len(records)} in-window records")

    run_id = f"oped-{senator_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    if not dry_run:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO scrape_runs (id, run_type) VALUES (%s, 'backfill')", (run_id,)
        )
        conn.commit()
        cur.close()

    counts = {
        "inserted_real": 0,
        "inserted_migration": 0,
        "skipped_dup": 0,
        "skipped_existing": 0,
        "skipped_pre_cutoff": 0,
    }

    for rec in records:
        link = rec.get("link")
        if not link:
            continue
        source_url = normalize_url(link)
        slug = rec.get("slug", "")
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

        stamped = bool(migration_prefix) and is_migration_stamped(rec, migration_prefix)
        if stamped and NUMBERED_SUFFIX.search(slug):
            counts["skipped_dup"] += 1
            continue

        date_source = "wp_modified_migration" if stamped else "wp_json"
        date_confidence = 0.3 if stamped else 1.0

        title_raw = rec.get("title", {})
        title = title_raw.get("rendered") if isinstance(title_raw, dict) else (title_raw or "")
        title = BeautifulSoup(title or "", "lxml").get_text(strip=True)
        if len(title) < 5:
            continue

        content_raw = rec.get("content", {})
        content_html = content_raw.get("rendered") if isinstance(content_raw, dict) else ""
        body_text = html_to_text(content_html)

        if dry_run:
            tag = "MIGR" if stamped else "REAL"
            print(f"    [{tag}] {pub_dt.date()} | {title[:75]}")
            continue

        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO press_releases
                  (senator_id, title, published_at, body_text, source_url,
                   scrape_run, content_type, date_source, date_confidence)
                VALUES (%s, %s, %s, %s, %s, %s, 'op_ed', %s, %s)
                ON CONFLICT (source_url) DO NOTHING
                """,
                (
                    senator_id,
                    title,
                    pub_dt,
                    body_text or None,
                    source_url,
                    run_id,
                    date_source,
                    date_confidence,
                ),
            )
            conn.commit()
            if cur.rowcount > 0:
                counts["inserted_migration" if stamped else "inserted_real"] += 1
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
    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    print("Probing WP-JSON op_eds endpoints...")
    senators = candidate_senators()
    print(f"  {len(senators)} senators expose /wp/v2/op_eds")

    if args.senator:
        senators = [s for s in senators if s["senator_id"] == args.senator]
        if not senators:
            print(f"  {args.senator} does not expose /wp/v2/op_eds")
            return

    grand = {
        "inserted_real": 0,
        "inserted_migration": 0,
        "skipped_dup": 0,
        "skipped_existing": 0,
        "skipped_pre_cutoff": 0,
    }
    for s in senators:
        c = collect_for(conn, s["senator_id"], s["base"], args.dry_run)
        for k in grand:
            grand[k] += c[k]

    print(f"\nGRAND TOTAL: {grand}")
    conn.close()


if __name__ == "__main__":
    main()
