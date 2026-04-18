"""
Capitol Releases -- Playwright Backfill for AJAX-Paginated Senators

For senators whose press release pages use JetEngine AJAX pagination
(click-based, no real URLs), this script uses a headless browser to
click through pagination and extract all releases.

Usage:
    python backfill_playwright.py
    python backfill_playwright.py --senators schmitt-eric
    python backfill_playwright.py --max-pages 50
"""

import json
import logging
import os
import re
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import psycopg2
from playwright.sync_api import sync_playwright

log = logging.getLogger("capitol.playwright")

# Load .env file if present
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.environ["DATABASE_URL"]

CUTOFF = datetime(2025, 1, 1, tzinfo=timezone.utc)

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

# The 5 AJAX senators
AJAX_SENATORS = [
    {"id": "schmitt-eric", "url": "https://www.schmitt.senate.gov/media/press-releases/"},
    {"id": "tuberville-tommy", "url": "https://www.tuberville.senate.gov/newsroom/press-releases/"},
    {"id": "young-todd", "url": "https://www.young.senate.gov/newsroom/press-releases/"},
    {"id": "scott-tim", "url": "https://www.scott.senate.gov/media-center/press-releases/"},
    {"id": "whitehouse-sheldon", "url": "https://www.whitehouse.senate.gov/news/release/"},
]


def parse_date(text):
    if not text:
        return None
    text = text.strip()
    m = re.search(r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*)\s+(\d{1,2}),?\s+(\d{4})", text, re.I)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(2)), tzinfo=timezone.utc)
            except ValueError:
                pass
    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})", text)
    if m:
        try:
            year = int(m.group(3))
            if year < 100:
                year += 2000
            return datetime(year, int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc)
        except ValueError:
            pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def scrape_senator_with_browser(page, senator_id, url, max_pages, run_id):
    """Use Playwright to scrape a JetEngine-paginated senator page."""
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True

    print(f"\n  [{senator_id}] Loading {url}")
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    inserted = 0
    skipped = 0
    page_num = 0
    stop = False

    while page_num < max_pages and not stop:
        page_num += 1

        # Extract items from current page
        items = page.query_selector_all(".jet-listing-grid__item")
        if not items:
            # Try alternative selectors
            items = page.query_selector_all("[class*='e-loop-item']")
        if not items:
            items = page.query_selector_all("article")

        if not items:
            print(f"    Page {page_num}: no items found")
            break

        for item in items:
            # Extract title and link
            title = ""
            detail_url = ""
            date_text = ""

            # Try h3/h4 with links
            for sel in ["h3 a", "h4 a", "h2 a", "a.jet-listing-dynamic-link__link"]:
                link = item.query_selector(sel)
                if link:
                    title = link.inner_text().strip()
                    href = link.get_attribute("href")
                    if title and len(title) > 10 and href:
                        detail_url = href
                        break

            # Fallback: first substantial link
            if not title:
                for link in item.query_selector_all("a[href]"):
                    t = link.inner_text().strip()
                    h = link.get_attribute("href") or ""
                    if len(t) > 15 and "senate.gov" in h and not any(s in t.lower() for s in ["home", "about", "contact", "menu"]):
                        title = t
                        detail_url = h
                        break

            # Extract date
            for sel in ["time", "[class*='date']", "[class*='Date']", "span"]:
                el = item.query_selector(sel)
                if el:
                    t = el.inner_text().strip()
                    if parse_date(t):
                        date_text = t
                        break

            if not date_text:
                # Try to find date in item text
                full_text = item.inner_text()
                date_match = re.search(
                    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}|"
                    r"\d{1,2}/\d{1,2}/\d{2,4}",
                    full_text
                )
                if date_match:
                    date_text = date_match.group(0)

            if not title or len(title) < 5 or not detail_url:
                continue

            pub_date = parse_date(date_text)

            # Check cutoff
            if pub_date and pub_date < CUTOFF:
                stop = True
                break

            # Check if exists
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM press_releases WHERE source_url = %s", (detail_url,))
            if cur.fetchone():
                skipped += 1
                cur.close()
                continue
            cur.close()

            # Fetch body text from detail page (quick visit)
            body_text = ""
            try:
                detail_page = page.context.new_page()
                detail_page.goto(detail_url, wait_until="domcontentloaded", timeout=15000)
                # Try common body selectors
                for sel in ["article .entry-content", ".post-content", "main article", ".bodycopy", "main .content"]:
                    el = detail_page.query_selector(sel)
                    if el:
                        body_text = el.inner_text().strip()
                        if len(body_text) > 100:
                            break
                if not body_text:
                    main = detail_page.query_selector("main") or detail_page.query_selector("article")
                    if main:
                        body_text = main.inner_text().strip()[:5000]
                detail_page.close()
            except Exception as e:
                log.warning("Detail page failed for %s: %s: %s", detail_url, type(e).__name__, e)
                try:
                    detail_page.close()
                except Exception:
                    pass  # page may already be closed

            # Insert
            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO press_releases (senator_id, title, published_at, body_text, source_url, scrape_run)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_url) DO NOTHING
                """, (senator_id, title, pub_date, body_text or None, detail_url, run_id))
                if cur.rowcount > 0:
                    inserted += 1
                    date_str = pub_date.strftime("%Y-%m-%d") if pub_date else "no date"
                    print(f"    + {date_str} | {title[:65]}")
            except Exception as e:
                print(f"    ERR: {e}")
            finally:
                cur.close()

        # Click next page
        if stop:
            break

        next_btn = page.query_selector(".jet-filters-pagination__item.prev-next.next .jet-filters-pagination__link")
        if not next_btn:
            # Try alternative next buttons
            next_btn = page.query_selector("[class*='pagination'] [class*='next']")
        if not next_btn:
            break

        try:
            next_btn.click()
            page.wait_for_timeout(2000)
            # Wait for content to update
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            print(f"    Pagination click failed: {e}")
            break

    conn.close()
    print(f"  [{senator_id}] {inserted} inserted, {skipped} skipped, {page_num} pages")
    return inserted, skipped


def main():
    parser = argparse.ArgumentParser(description="Playwright backfill for AJAX senators")
    parser.add_argument("--senators", nargs="*", help="Specific senator IDs")
    parser.add_argument("--max-pages", type=int, default=50)
    args = parser.parse_args()

    senators = AJAX_SENATORS
    if args.senators:
        senators = [s for s in AJAX_SENATORS if s["id"] in args.senators]

    run_id = f"playwright-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"

    print(f"\n{'='*60}")
    print(f"  PLAYWRIGHT BACKFILL")
    print(f"  Run: {run_id}")
    print(f"  Senators: {len(senators)}")
    print(f"  Max pages: {args.max_pages}")
    print(f"{'='*60}")

    total_inserted = 0
    total_skipped = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for senator in senators:
            try:
                ins, skip = scrape_senator_with_browser(
                    page, senator["id"], senator["url"], args.max_pages, run_id
                )
                total_inserted += ins
                total_skipped += skip
            except Exception as e:
                print(f"  [{senator['id']}] ERROR: {type(e).__name__}: {e}")

        browser.close()

    print(f"\n{'='*60}")
    print(f"  DONE: {total_inserted} inserted, {total_skipped} skipped")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
