"""Year/month archive backfill for the 'default_v7' theme group.

Discovery 2026-05-03: 6 House members on the legacy 'default_v7' shared
theme — previously classified pagination_js_required because ?page=N
returns the same 20 items at every depth — actually expose a working
date filter at ?year=YYYY&month=MM. Iterating year × month yields
full archive coverage without browser automation.

Members confirmed working with this pattern:
  auchincloss-jake, levin-mike, tokuda-jill, menendez-robert,
  mciver-lamonica, moore-blake

Each listing item is rendered as <h2 class="title"><a>title</a></h2>
inside a generic div. Date is sometimes adjacent (need extraction).
We pair the title link with the document detail page and extract
the date from there.
"""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
import psycopg2
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.__main__ import _load_dotenv

_load_dotenv()

DB_URL = os.environ["DATABASE_URL"]
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}

CUTOFF = datetime(2025, 1, 1, tzinfo=timezone.utc)

MEMBERS = [
    ("auchincloss-jake", "https://auchincloss.house.gov"),
    ("levin-mike",       "https://levin.house.gov"),
    ("tokuda-jill",      "https://tokuda.house.gov"),
    ("menendez-robert",  "https://menendez.house.gov"),
    ("mciver-lamonica",  "https://mciver.house.gov"),
    ("moore-blake",      "https://blakemoore.house.gov"),
]


_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})\b"
)


def parse_listing(html: str, base: str) -> list[tuple[str, str]]:
    """Return [(title, detail_url), ...] from a listing page."""
    soup = BeautifulSoup(html, "lxml")
    out: list[tuple[str, str]] = []
    for h2 in soup.select("h2.title"):
        a = h2.find("a", href=True)
        if not a:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 5:
            continue
        href = a["href"]
        detail_url = urljoin(base, href)
        if "/press-releases/" not in detail_url and "/media/" not in detail_url:
            continue
        out.append((title, detail_url))
    return out


def fetch_detail_date_and_body(client: httpx.Client, url: str) -> tuple[datetime | None, str | None]:
    """Visit detail page, extract date string + body."""
    try:
        r = client.get(url, timeout=12.0)
    except Exception:
        return None, None
    if r.status_code != 200:
        return None, None
    soup = BeautifulSoup(r.text, "lxml")

    # Try common date locations
    date_str = None
    for sel in ["time[datetime]", ".date", ".article-date", ".release-date", ".meta-date"]:
        el = soup.select_one(sel)
        if el:
            text = el.get("datetime") or el.get_text(" ", strip=True)
            if text:
                date_str = text
                break

    # Fallback: regex over body for "Month DD, YYYY"
    if not date_str:
        m = _DATE_RE.search(soup.get_text(" ", strip=True))
        if m:
            date_str = m.group(0)

    pub_dt = None
    if date_str:
        # Try ISO first
        try:
            pub_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    if not pub_dt and date_str:
        try:
            pub_dt = datetime.strptime(date_str.split(",")[0] + "," + date_str.split(",")[1].strip()[:5], "%B %d, %Y").replace(tzinfo=timezone.utc)
        except Exception:
            try:
                pub_dt = datetime.strptime(date_str.strip(), "%B %d, %Y").replace(tzinfo=timezone.utc)
            except Exception:
                m = _DATE_RE.search(date_str)
                if m:
                    try:
                        pub_dt = datetime.strptime(f"{m.group(1)} {m.group(2)}, {m.group(3)}", "%B %d, %Y").replace(tzinfo=timezone.utc)
                    except Exception:
                        pass

    # Body
    body = ""
    for sel in [".article-body", ".content", "main", "article", ".press-release-content"]:
        el = soup.select_one(sel)
        if el:
            body = el.get_text(" ", strip=True)
            if len(body) > 100:
                break
    if not body:
        body = soup.get_text(" ", strip=True)
    return pub_dt, body[:50000] if body else None


def collect_member(conn, client, mid: str, base: str, run_id: str) -> dict:
    counts = {"pages_walked": 0, "items_found": 0, "inserted": 0,
              "skipped_existing": 0, "skipped_no_date": 0, "skipped_pre_cutoff": 0}
    print(f"\n[{mid}] {base}")
    seen_urls: set[str] = set()
    # Iterate 2025-01 .. 2026-12. Stops mostly because empty months are quick.
    for year in (2025, 2026):
        for month in range(1, 13):
            url = f"{base}/media/press-releases?year={year}&month={month:02d}"
            try:
                r = client.get(url, timeout=12.0)
            except Exception:
                continue
            counts["pages_walked"] += 1
            if r.status_code != 200:
                continue
            items = parse_listing(r.text, base)
            for title, detail_url in items:
                if detail_url in seen_urls:
                    continue
                seen_urls.add(detail_url)
                counts["items_found"] += 1

                # Already in DB?
                cur = conn.cursor()
                cur.execute(
                    "SELECT id FROM official_site_items WHERE source_url = %s",
                    (detail_url,),
                )
                existing = cur.fetchone()
                cur.close()
                if existing:
                    counts["skipped_existing"] += 1
                    continue

                pub_dt, body = fetch_detail_date_and_body(client, detail_url)
                if not pub_dt:
                    counts["skipped_no_date"] += 1
                    continue
                if pub_dt < CUTOFF:
                    counts["skipped_pre_cutoff"] += 1
                    continue

                cur = conn.cursor()
                try:
                    cur.execute(
                        """
                        INSERT INTO official_site_items
                          (official_id, title, published_at, body_text, source_url,
                           scrape_run, content_type, date_source, date_confidence)
                        VALUES (%s, %s, %s, %s, %s, %s, 'press_release', 'detail_page', 0.9)
                        ON CONFLICT (source_url) DO NOTHING
                        """,
                        (mid, title, pub_dt, body, detail_url, run_id),
                    )
                    conn.commit()
                    if cur.rowcount:
                        counts["inserted"] += 1
                except Exception as e:
                    print(f"  err: {e}")
                    conn.rollback()
                finally:
                    cur.close()
                time.sleep(0.2)
            time.sleep(0.3)
    print(f"  {counts}")
    return counts


def main():
    print(f"default_v7 archive backfill — {len(MEMBERS)} members")
    conn = psycopg2.connect(DB_URL)
    run_id = f"default-v7-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    cur = conn.cursor()
    cur.execute("INSERT INTO scrape_runs (id, run_type) VALUES (%s, 'backfill')", (run_id,))
    conn.commit()
    cur.close()

    grand = {"pages_walked": 0, "items_found": 0, "inserted": 0,
             "skipped_existing": 0, "skipped_no_date": 0, "skipped_pre_cutoff": 0}
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for mid, base in MEMBERS:
            counts = collect_member(conn, client, mid, base, run_id)
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
