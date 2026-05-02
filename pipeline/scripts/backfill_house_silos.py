"""House silo backfill — op-eds, columns, blogs, newsletters, speeches, etc.

Mirrors pipeline/scripts/backfill_silos.py for Senate, with House-shaped
inputs:

  - Silo list comes from pipeline/recon/house_full_recon.json (output of
    house_full_recon.py), filtered to channels where:
        * is_listing == True
        * not rejected
        * status_code == 200
        * content_type in {op_ed, blog, newsletter, floor_statement,
                           statement, letter}   (press_release is
                           handled by the main backfill.py path)
  - Each silo carries its own selectors + pagination from the recon, so
    the script does not have to re-load anything from house.json.
  - Insert host filter is `.house.gov` instead of `.senate.gov`.

Records land in press_releases with the right `content_type` and
`date_source='silo_backfill'`, dedup'd by `source_url` (which has a
unique constraint).

Usage:
    python -m pipeline.scripts.backfill_house_silos                       # all silos
    python -m pipeline.scripts.backfill_house_silos --member palmer-gary  # one member
    python -m pipeline.scripts.backfill_house_silos --content-type op_ed
    python -m pipeline.scripts.backfill_house_silos --dry-run --max-pages 3
    python -m pipeline.scripts.backfill_house_silos --limit 5             # first 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import psycopg2
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.backfill import (  # noqa: E402
    extract_listing_items,
    extract_item_data,
    find_next_page,
    parse_date,
)
from pipeline.backfill_wp_json import load_env, normalize_url  # noqa: E402

CUTOFF = date(2025, 1, 1)
RECON_FILE = ROOT / "pipeline" / "recon" / "house_full_recon.json"

# Same Akamai-safe header set used by the recon and house_rss_probe.
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not_A Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# content_types we collect via silos. press_release is excluded — it goes
# through pipeline/backfill.py from the senators table.
SILO_CONTENT_TYPES = {
    "op_ed",
    "blog",
    "newsletter",
    "floor_statement",
    "statement",
    "letter",
}


def load_silos() -> list[dict]:
    """Read house_full_recon.json and return the per-silo records.

    Each returned dict is:
      {
        member_id, full_name, state, district,
        url, content_type, selectors, pagination,
      }
    """
    if not RECON_FILE.exists():
        raise SystemExit(
            f"{RECON_FILE} missing. Run pipeline/recon/house_full_recon.py first."
        )
    recon = json.loads(RECON_FILE.read_text())
    out: list[dict] = []
    for r in recon["results"]:
        for c in r.get("channels", []):
            if not c.get("is_listing") or c.get("rejected") or c.get("status_code") != 200:
                continue
            ct = c.get("content_type")
            if ct not in SILO_CONTENT_TYPES:
                continue
            out.append({
                "member_id": r["member_id"],
                "full_name": r.get("full_name", ""),
                "state": r.get("state", ""),
                "district": r.get("district"),
                "url": c["url"],
                "content_type": ct,
                "selectors": c.get("selectors") or {},
                "pagination": c.get("pagination"),
            })
    return out


def collect_silo(
    conn,
    client: httpx.Client,
    silo: dict,
    max_pages: int,
    dry_run: bool,
) -> dict:
    member_id = silo["member_id"]
    section_url = silo["url"]
    content_type = silo["content_type"]
    selectors = silo["selectors"]

    print(f"\n[{member_id}] {section_url}  ({content_type})")
    counts = {
        "pages_walked": 0,
        "items_seen": 0,
        "inserted": 0,
        "skipped_existing": 0,
        "skipped_pre_cutoff": 0,
        "skipped_no_date": 0,
        "skipped_short": 0,
        "skipped_off_host": 0,
    }

    run_id = f"silo-{member_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    if not dry_run:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO scrape_runs (id, run_type) VALUES (%s, 'backfill')",
            (run_id,),
        )
        conn.commit()
        cur.close()

    current = section_url
    page = 0
    seen_urls: set[str] = set()
    while current and page < max_pages:
        page += 1
        try:
            r = client.get(current, follow_redirects=True)
        except Exception as e:
            print(f"  page {page} fetch err: {type(e).__name__}: {e}")
            break
        if r.status_code != 200:
            print(f"  page {page} status {r.status_code}")
            break
        soup = BeautifulSoup(r.text, "lxml")
        items = extract_listing_items(soup, selectors)
        if not items:
            print(f"  page {page}: no items found (selectors may not match)")
            break
        print(f"  page {page}: {len(items)} items")
        counts["pages_walked"] += 1

        for it in items:
            counts["items_seen"] += 1
            try:
                title, date_text, detail = extract_item_data(it, section_url, selectors)
            except Exception:
                continue
            title = (title or "").strip()
            date_text = (date_text or "").strip()
            detail = (detail or "").strip()
            if not detail or not title or len(title) < 3:
                counts["skipped_short"] += 1
                continue
            detail = normalize_url(detail)
            if detail in seen_urls:
                continue
            seen_urls.add(detail)
            # Same-host check: House offices live under *.house.gov. Reject
            # external links (op-eds linking to a newspaper site, etc.).
            if ".house.gov" not in detail:
                counts["skipped_off_host"] += 1
                continue

            pub_dt = parse_date(date_text) if date_text else None
            if not pub_dt:
                counts["skipped_no_date"] += 1
                continue
            if isinstance(pub_dt, date) and not isinstance(pub_dt, datetime):
                pub_dt = datetime.combine(pub_dt, datetime.min.time(), tzinfo=timezone.utc)
            if pub_dt.date() < CUTOFF:
                counts["skipped_pre_cutoff"] += 1
                continue

            if dry_run:
                print(f"    {pub_dt.date()} | {title[:80]}")
                continue

            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO press_releases
                      (senator_id, title, published_at, source_url,
                       scrape_run, content_type, date_source, date_confidence)
                    VALUES (%s, %s, %s, %s, %s, %s, 'silo_backfill', 0.9)
                    ON CONFLICT (source_url) DO NOTHING
                    """,
                    (member_id, title, pub_dt, detail, run_id, content_type),
                )
                conn.commit()
                if cur.rowcount > 0:
                    counts["inserted"] += 1
                else:
                    counts["skipped_existing"] += 1
            except Exception as e:
                conn.rollback()
                print(f"    ERR on {detail}: {e}")
            finally:
                cur.close()

        nxt = find_next_page(soup, current)
        if not nxt or nxt == current:
            break
        current = nxt

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--member", help="Run only for one member_id")
    ap.add_argument(
        "--content-type",
        choices=sorted(SILO_CONTENT_TYPES),
        help="Run only silos of this type",
    )
    ap.add_argument("--limit", type=int, help="Process only the first N silos (after filters)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-pages", type=int, default=10)
    args = ap.parse_args()

    load_env()

    silos = load_silos()
    if args.member:
        silos = [s for s in silos if s["member_id"] == args.member]
    if args.content_type:
        silos = [s for s in silos if s["content_type"] == args.content_type]
    if args.limit:
        silos = silos[: args.limit]
    if not silos:
        print("no matching silos")
        return

    print(f"Will process {len(silos)} silos (max_pages={args.max_pages}, dry_run={args.dry_run})")
    from collections import Counter
    by_ct = Counter(s["content_type"] for s in silos)
    for ct, n in by_ct.most_common():
        print(f"  {ct:<18} {n}")

    conn = None if args.dry_run else psycopg2.connect(os.environ["DATABASE_URL"])

    grand = {
        "items_seen": 0,
        "inserted": 0,
        "skipped_existing": 0,
        "skipped_pre_cutoff": 0,
        "skipped_no_date": 0,
        "skipped_short": 0,
        "skipped_off_host": 0,
    }
    with httpx.Client(timeout=25.0, headers=BROWSER_HEADERS, follow_redirects=True) as client:
        for silo in silos:
            counts = collect_silo(conn, client, silo, args.max_pages, args.dry_run)
            for k in grand:
                grand[k] += counts.get(k, 0)

    if conn:
        conn.close()
    print(f"\nGRAND TOTAL: {grand}")


if __name__ == "__main__":
    main()
