"""Paginated RSS backfill for NextJS+GraphQL House members on WordPress.

Yesterday's recon flagged 19 House members on a shared NextJS+WPGraphQL
stack as 'playwright_required' because the public site only SSRs ~10
items per page and the GraphQL admin endpoint isn't publicly addressable.

Discovery 2026-05-03: 16 of those 19 expose a standard WordPress RSS
feed at /feed that supports `?paged=N` pagination. Walking paged=1 .. N
yields the full archive without browser automation. Only 3 members
(donalds-byron, guthrie-brett, meeks-gregory) genuinely lack a feed
and remain playwright_required.

This script walks /feed?paged=N for each member until either:
  - RSS returns no entries
  - The oldest entry on a page is before the cutoff (2025-01-01)
  - We hit MAX_PAGED (safety net)

Each entry becomes an official_site_items row tagged with
date_source='rss_feed' and date_confidence=0.95.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import feedparser
import psycopg2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.__main__ import _load_dotenv

_load_dotenv()

DB_URL = os.environ["DATABASE_URL"]

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept": "*/*"}

CUTOFF = datetime(2025, 1, 1, tzinfo=timezone.utc)
MAX_PAGED = 30  # 30 pages × 10 items = up to 300 records per member

# 16 NextJS+GraphQL House members confirmed to have working /feed
# (probed 2026-05-03). Format: (member_id, base_url).
MEMBERS = [
    ("kiley-kevin",        "https://kiley.house.gov"),
    ("luna-anna",          "https://luna.house.gov"),
    ("moskowitz-jared",    "https://moskowitz.house.gov"),
    ("williams-nikema",    "https://nikemawilliams.house.gov"),
    ("budzinski-nikki",    "https://budzinski.house.gov"),
    ("yakym-rudy",         "https://yakym.house.gov"),
    ("tlaib-rashida",      "https://tlaib.house.gov"),
    ("gottheimer-josh",    "https://gottheimer.house.gov"),
    ("torres-ritchie",     "https://ritchietorres.house.gov"),
    ("landsman-greg",      "https://landsman.house.gov"),
    ("miller-max",         "https://maxmiller.house.gov"),
    ("joyce-david",        "https://joyce.house.gov"),
    ("lucas-frank",        "https://lucas.house.gov"),
    ("cloud-michael",      "https://cloud.house.gov"),
    ("owens-burgess",      "https://owens.house.gov"),
    ("perez-marie",        "https://gluesenkampperez.house.gov"),
]


def parse_pubdate(raw: str) -> datetime | None:
    """RFC-822 date parser; feedparser already does this for us if available."""
    if not raw:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def fetch_page(client: httpx.Client, base: str, paged: int) -> tuple[list[dict], bool]:
    """Fetch one paged RSS. Returns (entries, is_terminal_page).

    is_terminal_page=True when the page has fewer than 10 entries OR
    the oldest entry is at/before CUTOFF — caller stops walking.
    """
    url = f"{base}/feed" if paged <= 1 else f"{base}/feed?paged={paged}"
    try:
        r = client.get(url, timeout=15.0)
    except Exception:
        return [], True
    if r.status_code != 200:
        return [], True
    feed = feedparser.parse(r.text)
    items: list[dict] = []
    oldest = None
    for e in feed.entries:
        title = e.get("title") or ""
        link = e.get("link") or ""
        pub_raw = e.get("published") or e.get("updated") or ""
        dt = parse_pubdate(pub_raw)
        if not (title and link and dt):
            continue
        if oldest is None or dt < oldest:
            oldest = dt
        # Body: feedparser puts content in different fields depending on
        # CDATA encoding. Try content > summary > description.
        body = ""
        if e.get("content"):
            body = e["content"][0].get("value", "") if isinstance(e["content"], list) else ""
        if not body:
            body = e.get("summary") or e.get("description") or ""
        items.append(
            {
                "title": title.strip(),
                "source_url": link,
                "published_at": dt,
                "body_text": body[:50000] if body else None,
            }
        )
    is_terminal = len(items) < 10 or (oldest is not None and oldest < CUTOFF)
    return items, is_terminal


def collect_member(conn, client, member_id: str, base: str, run_id: str) -> dict:
    counts = {"pages_walked": 0, "items_seen": 0, "inserted": 0,
              "skipped_existing": 0, "skipped_pre_cutoff": 0}
    print(f"\n[{member_id}] {base}/feed")
    for paged in range(1, MAX_PAGED + 1):
        items, terminal = fetch_page(client, base, paged)
        counts["pages_walked"] += 1
        counts["items_seen"] += len(items)
        if not items:
            break
        for it in items:
            if it["published_at"] < CUTOFF:
                counts["skipped_pre_cutoff"] += 1
                continue
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO official_site_items
                      (official_id, title, published_at, body_text, source_url,
                       scrape_run, content_type, date_source, date_confidence)
                    VALUES (%s, %s, %s, %s, %s, %s, 'press_release', 'rss_feed', 0.95)
                    ON CONFLICT (source_url) DO NOTHING
                    """,
                    (
                        member_id,
                        it["title"],
                        it["published_at"],
                        it["body_text"],
                        it["source_url"],
                        run_id,
                    ),
                )
                conn.commit()
                if cur.rowcount:
                    counts["inserted"] += 1
                else:
                    counts["skipped_existing"] += 1
            except Exception as e:
                print(f"  err {it['source_url']}: {e}")
                conn.rollback()
            finally:
                cur.close()
        if terminal:
            break
        time.sleep(0.5)  # politeness
    print(f"  {counts}")
    return counts


def main():
    print(f"WordPress paginated-RSS backfill — {len(MEMBERS)} House members")
    conn = psycopg2.connect(DB_URL)
    run_id = f"wp-rss-paged-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    cur = conn.cursor()
    cur.execute("INSERT INTO scrape_runs (id, run_type) VALUES (%s, 'backfill')", (run_id,))
    conn.commit()
    cur.close()

    grand = {"pages_walked": 0, "items_seen": 0, "inserted": 0,
             "skipped_existing": 0, "skipped_pre_cutoff": 0}
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for member_id, base in MEMBERS:
            counts = collect_member(conn, client, member_id, base, run_id)
            for k in grand:
                grand[k] += counts.get(k, 0)

    cur = conn.cursor()
    import json
    cur.execute(
        "UPDATE scrape_runs SET finished_at = NOW(), stats = %s::jsonb WHERE id = %s",
        (json.dumps(grand), run_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"\nGRAND TOTAL: {grand}")


if __name__ == "__main__":
    main()
