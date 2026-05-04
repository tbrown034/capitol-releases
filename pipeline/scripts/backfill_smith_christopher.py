"""One-off collector for Chris Smith (R-NJ-4) — chrissmith.house.gov.

Smith's site is a unique ASP.NET CMS that mixes original press output
with third-party news clippings on the same listing. The list page is
`documentquery.aspx?Year=YYYY[&Page=N]` and each item carries a
"Posted in [Category] on [Date]" line that classifies the item.

Categories observed:
  Press Release                            -> KEEP (content_type='press_release')
  Statements                               -> KEEP (content_type='statement')
  Remarks by Congressman Smith             -> KEEP (content_type='floor_statement')
  Opinion Pieces                           -> KEEP (content_type='op_ed')
  Committee Hearing Opening Statements     -> KEEP (content_type='floor_statement')
  Hearings                                 -> KEEP (content_type='other')
  In the Press...                          -> SKIP (third-party clipping)

Each year archive has ~14-33 pages (10 items per page).

Run: python -m pipeline.scripts.backfill_smith_christopher
"""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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

CUTOFF_DATE = datetime(2025, 1, 1, tzinfo=timezone.utc)
BASE = "https://chrissmith.house.gov"

# Map "Posted in" category text to our content_type taxonomy.
CATEGORY_MAP = {
    "press release": "press_release",
    "statements": "statement",
    "remarks by congressman smith": "floor_statement",
    "opinion pieces": "op_ed",
    "committee hearing opening statements": "floor_statement",
    "hearings": "other",
}
SKIP_CATEGORIES = {"in the press"}  # third-party clippings


_POSTED_IN_RE = re.compile(
    r"Posted in (.+?) on ([A-Za-z]+ \d+, \d{4})", re.MULTILINE
)


def parse_posted_in(li_text: str) -> tuple[str, datetime] | None:
    """Pull the (category_norm, parsed_datetime) out of a list-item's text."""
    m = _POSTED_IN_RE.search(li_text)
    if not m:
        return None
    raw_cat = m.group(1).strip().rstrip(".").lower()
    raw_cat = raw_cat.replace("...", "").strip()
    raw_date = m.group(2)
    try:
        dt = datetime.strptime(raw_date, "%B %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return raw_cat, dt


def fetch_page(client: httpx.Client, year: int, page: int) -> list[dict]:
    """Return list of item dicts for a (year, page). Empty list = no more.

    Smith's listing has all items inside ONE outer <li> separated by <br/>.
    So instead of iterating list items, we iterate the title anchors
    (a.middleheadline) and walk siblings forward until the next anchor to
    find the "Posted in X on DATE" text that belongs to each title.
    """
    if page <= 1:
        url = f"{BASE}/news/documentquery.aspx?Year={year}"
    else:
        url = f"{BASE}/news/documentquery.aspx?Year={year}&Page={page}"
    r = client.get(url, timeout=15.0)
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "lxml")

    items_out: list[dict] = []
    title_anchors = soup.select(
        "ul.UnorderedNewsList a.middleheadline[href*='documentsingle.aspx']"
    )
    for a in title_anchors:
        title = a.get_text(strip=True)
        if not title or len(title) < 4:
            continue
        href = a.get("href") or ""
        if href.startswith("/"):
            detail_url = f"{BASE}{href}"
        elif not href.startswith("http"):
            detail_url = f"{BASE}/news/{href}"
        else:
            detail_url = href

        # Walk forward through siblings until we hit the next title anchor
        # OR find the "Posted in X on DATE" text. Concat sibling text.
        chunk: list[str] = []
        for sib in a.next_siblings:
            sib_text = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else (str(sib).strip() if hasattr(sib, "strip") else "")
            if not sib_text:
                continue
            # Stop if we hit another title anchor's container
            if hasattr(sib, "select_one") and sib.select_one("a.middleheadline"):
                break
            chunk.append(sib_text)
            if "Posted in" in sib_text:
                break

        meta = parse_posted_in(" ".join(chunk))
        if not meta:
            continue
        cat_norm, dt = meta
        if cat_norm in SKIP_CATEGORIES:
            continue
        content_type = CATEGORY_MAP.get(cat_norm, "other")
        items_out.append(
            {
                "title": title,
                "source_url": detail_url,
                "published_at": dt,
                "content_type": content_type,
                "raw_category": cat_norm,
            }
        )
    return items_out


def fetch_body(client: httpx.Client, source_url: str) -> str | None:
    try:
        r = client.get(source_url, timeout=15.0)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "lxml")
        body_el = soup.select_one(".middlecopy") or soup.select_one("body")
        if not body_el:
            return None
        text = body_el.get_text(" ", strip=True)
        return text[:50000] if text else None
    except Exception:
        return None


def main():
    print("Smith-Christopher backfill — chrissmith.house.gov")
    conn = psycopg2.connect(DB_URL)
    run_id = f"smith-christopher-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    cur = conn.cursor()
    cur.execute("INSERT INTO scrape_runs (id, run_type) VALUES (%s, 'backfill')", (run_id,))
    conn.commit()
    cur.close()

    inserted = 0
    skipped_existing = 0
    skipped_clippings = 0
    skipped_pre_cutoff = 0
    pages_walked = 0
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for year in (2026, 2025):
            for page in range(1, 100):
                items = fetch_page(client, year, page)
                if not items:
                    break
                pages_walked += 1
                stop = False
                for it in items:
                    if it["published_at"] < CUTOFF_DATE:
                        skipped_pre_cutoff += 1
                        stop = True
                        continue
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id FROM official_site_items WHERE source_url = %s",
                        (it["source_url"],),
                    )
                    existing = cur.fetchone()
                    cur.close()
                    if existing:
                        skipped_existing += 1
                        continue
                    body = fetch_body(client, it["source_url"])
                    cur = conn.cursor()
                    try:
                        cur.execute(
                            """
                            INSERT INTO official_site_items
                              (official_id, title, published_at, body_text, source_url,
                               scrape_run, content_type, date_source, date_confidence)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, 'listing_page', 0.95)
                            ON CONFLICT (source_url) DO NOTHING
                            """,
                            (
                                "smith-christopher",
                                it["title"],
                                it["published_at"],
                                body,
                                it["source_url"],
                                run_id,
                                it["content_type"],
                            ),
                        )
                        conn.commit()
                        if cur.rowcount:
                            inserted += 1
                            print(f"  + {it['published_at'].strftime('%Y-%m-%d')} | {it['raw_category']:30s} | {it['title'][:55]}")
                    except Exception as e:
                        print(f"  err {it['source_url']}: {e}")
                        conn.rollback()
                    finally:
                        cur.close()
                    time.sleep(0.3)
                if stop:
                    # crossed the cutoff inside this page; don't continue further pages
                    break
                time.sleep(0.5)

    cur = conn.cursor()
    import json
    cur.execute(
        "UPDATE scrape_runs SET finished_at = NOW(), stats = %s::jsonb WHERE id = %s",
        (json.dumps({
            "inserted": inserted,
            "skipped_existing": skipped_existing,
            "skipped_clippings": skipped_clippings,
            "skipped_pre_cutoff": skipped_pre_cutoff,
            "pages_walked": pages_walked,
        }), run_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"\nDONE: {inserted} inserted, {skipped_existing} skipped (existing), "
          f"{skipped_pre_cutoff} skipped (pre-cutoff), {pages_walked} pages walked")


if __name__ == "__main__":
    main()
