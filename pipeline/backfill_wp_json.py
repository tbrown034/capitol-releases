"""Targeted backfill using the WordPress JSON API (`wp-json/wp/v2/...`).

Many senators' WP sites expose a `press_releases` (or `posts`) REST endpoint with
perfect pagination metadata (X-WP-Total, X-WP-TotalPages). This path is:
  - orders of magnitude cleaner than HTML scraping (structured title, date, body)
  - unaffected by HTML pagination caps (e.g. WP archives limited to 5 pages)
  - correctly typed dates (ISO-8601 UTC) so no date_source heuristics needed

This script is a focused rescue tool, not a general collector. Use it when a
WP senator's HTML-scraped count is suspiciously low AND /wp-json/wp/v2 exposes
a usable endpoint. It does NOT replace the daily updater -- that still reads
HTML. But for backfill depth, WP JSON wins.

Usage:
    python -m pipeline.backfill_wp_json --senator risch-james --endpoint press_releases
    python -m pipeline.backfill_wp_json --senator tuberville-tommy --endpoint press_releases
"""
import argparse
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import psycopg2
from bs4 import BeautifulSoup

CUTOFF_DATE = date(2025, 1, 1)


def load_env() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def normalize_url(url: str) -> str:
    return url.rstrip("/")


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(" ", strip=True)


def fetch_all(base_url: str, endpoint: str, per_page: int = 100) -> list[dict]:
    """Walk every page of a WP REST collection."""
    url = f"{base_url.rstrip('/')}/wp-json/wp/v2/{endpoint}"
    out: list[dict] = []
    page = 1
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        while True:
            r = client.get(url, params={"per_page": per_page, "page": page})
            if r.status_code == 400:
                break
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            out.extend(batch)
            total_pages = int(r.headers.get("X-WP-TotalPages", "0") or 0)
            print(f"  page {page}/{total_pages}: fetched {len(batch)} (running total {len(out)})")
            if page >= total_pages or len(batch) < per_page:
                break
            page += 1
    return out


def get_senator(conn, senator_id: str) -> dict:
    cur = conn.cursor()
    cur.execute(
        "SELECT id, full_name, official_url, press_release_url FROM senators WHERE id = %s",
        (senator_id,),
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        raise SystemExit(f"unknown senator_id: {senator_id}")
    return {"id": row[0], "full_name": row[1], "official_url": row[2], "press_release_url": row[3]}


def run(senator_id: str, endpoint: str) -> None:
    load_env()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    senator = get_senator(conn, senator_id)
    base_url = senator["official_url"] or re.sub(r"/[^/]+/?$", "/", senator["press_release_url"] or "")

    run_id = f"wpjson-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"
    cur = conn.cursor()
    cur.execute("INSERT INTO scrape_runs (id, run_type) VALUES (%s, 'backfill')", (run_id,))
    conn.commit()
    cur.close()

    print(f"\nFetching WP JSON for {senator['full_name']} -- endpoint={endpoint}")
    records = fetch_all(base_url, endpoint)
    print(f"Total fetched: {len(records)}")

    inserted = 0
    skipped_pre_cutoff = 0
    skipped_existing = 0
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
        pub_date = pub_dt.date()
        if pub_date < CUTOFF_DATE:
            skipped_pre_cutoff += 1
            continue

        title_raw = rec.get("title", {})
        title = title_raw.get("rendered") if isinstance(title_raw, dict) else (title_raw or "")
        title = BeautifulSoup(title or "", "lxml").get_text(strip=True)
        if len(title) < 5:
            continue

        content_raw = rec.get("content", {})
        content_html = content_raw.get("rendered") if isinstance(content_raw, dict) else ""
        body_text = html_to_text(content_html)

        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO press_releases (senator_id, title, published_at, body_text, source_url, scrape_run)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_url) DO NOTHING
                """,
                (senator_id, title, pub_dt, body_text or None, source_url, run_id),
            )
            conn.commit()
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped_existing += 1
        except Exception as e:
            conn.rollback()
            print(f"  ERR on {source_url}: {e}")
        finally:
            cur.close()

    cur = conn.cursor()
    cur.execute(
        "UPDATE scrape_runs SET finished_at = NOW(), stats = %s::jsonb WHERE id = %s",
        (
            f'{{"inserted":{inserted},"skipped_existing":{skipped_existing},"skipped_pre_cutoff":{skipped_pre_cutoff}}}',
            run_id,
        ),
    )
    conn.commit()
    cur.close()

    print(
        f"\nDone: inserted={inserted} skipped_existing={skipped_existing} "
        f"skipped_pre_cutoff={skipped_pre_cutoff}"
    )
    conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--senator", required=True, help="senator_id, e.g. risch-james")
    ap.add_argument("--endpoint", default="press_releases", help="WP REST collection name")
    args = ap.parse_args()
    run(args.senator, args.endpoint)


if __name__ == "__main__":
    main()
