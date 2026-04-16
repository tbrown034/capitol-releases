"""
Capitol Releases -- Backfill Script (Script 2)

Reads the senate seed config, scrapes press releases from each senator's
listing page, follows detail links for body text, and inserts into Postgres.

Usage:
    python backfill.py                          # all senators
    python backfill.py --senators daines-steve sanders-bernard
    python backfill.py --limit 5                # first 5 senators by confidence
    python backfill.py --max-pages 3            # limit pagination depth
"""

import asyncio
import json
import os
import re
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
import psycopg2
from bs4 import BeautifulSoup

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_CH7k3vjTsoRG@ep-young-tree-amictscx-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require",
)

MAX_CONCURRENT = 6
REQUEST_TIMEOUT = 20.0
CUTOFF_DATE = datetime(2025, 1, 1, tzinfo=timezone.utc)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

# Date parsing patterns
DATE_PATTERNS = [
    (re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})"), "mdy_numeric"),
    (re.compile(r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*)\s+(\d{1,2}),?\s+(\d{4})", re.I), "mdy_text"),
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "iso"),
]

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_date(text: str):
    """Try to parse a date from text. Returns datetime or None."""
    if not text:
        return None
    text = text.strip()
    for pattern, fmt in DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        try:
            if fmt == "mdy_numeric":
                month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if year < 100:
                    year += 2000
                return datetime(year, month, day, tzinfo=timezone.utc)
            elif fmt == "mdy_text":
                month = MONTH_MAP.get(m.group(1).lower()[:3])
                if month:
                    return datetime(int(m.group(3)), month, int(m.group(2)), tzinfo=timezone.utc)
            elif fmt == "iso":
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except (ValueError, KeyError):
            continue
    return None


def extract_listing_items(soup, selectors):
    """Extract press release items from a listing page."""
    # Senate custom CMS: ArticleBlock (covers ~30+ senators)
    # Check this FIRST -- many sites have bad recon selectors that match nav items
    items = soup.select(".ArticleBlock")
    if len(items) >= 2:
        return items

    # Elementor loop items (Banks, McCormick, etc.)
    items = soup.select("div.e-loop-item")
    if len(items) >= 2:
        return items

    # Senate legacy CMS: div.element (Rick Scott, Grassley, etc.)
    items = soup.select("div.element")
    if len(items) >= 2:
        return items

    # Try discovered selectors (but skip known-bad ones)
    list_sel = selectors.get("list_item")
    bad_selectors = {"span.elementor-grid-item", "li.page-item"}
    if list_sel and list_sel not in bad_selectors:
        items = soup.select(list_sel)
        if items:
            return items

    # Fallback selectors
    for sel in [
        "table.table-striped tbody tr", ".views-row", "article",
        ".element-list .element", "li.press-release", ".record",
        ".entry", ".list-item", ".news-item",
    ]:
        items = soup.select(sel)
        if len(items) >= 2:
            return items

    # Last resort: find all links to press-release detail pages
    base = soup.select_one("link[rel='canonical']")
    base_href = base["href"] if base else ""
    if base_href:
        pr_links = soup.select(f"a[href*='{base_href.split('/newsroom')[0]}']")
        pr_links = [a for a in pr_links if len(a.get_text(strip=True)) > 20
                    and a.parent.name not in ("nav", "header", "footer")
                    and "menu-item" not in " ".join(a.parent.get("class", []))]
        if len(pr_links) >= 3:
            return pr_links

    return []


def extract_item_data(item, base_url, selectors):
    """Extract title, date, detail_link from a listing item."""
    title = ""
    date_text = ""
    detail_url = ""

    # Senate custom CMS: ArticleBlock pattern
    article_link = item.select_one(".ArticleTitle a, .ArticleTitle__link, a.ArticleTitle__link")
    if article_link:
        title = article_link.get_text(strip=True)
        href = article_link.get("href", "")
        if href:
            detail_url = urljoin(base_url, href)
        date_el = item.select_one(".ArticleBlock__date")
        if date_el:
            date_text = date_el.get_text(strip=True)
        return title, date_text, detail_url

    # Elementor loop item pattern (e.g., Banks)
    if "e-loop-item" in " ".join(item.get("class", [])):
        # Title is in an anchor with heading inside, or the first substantial link
        for el in item.select("a"):
            text = el.get_text(strip=True)
            href = el.get("href", "")
            if len(text) > 15 and href and "senate.gov" in href and not any(s in text.lower() for s in ["home", "about", "contact", "menu"]):
                title = text
                detail_url = urljoin(base_url, href)
                break
        # Date from post-info widget
        info = item.select_one(".elementor-widget-post-info")
        if info:
            date_text = info.get_text(strip=True)
        if not date_text:
            block = item.get_text(" ", strip=True)
            for pat, _ in DATE_PATTERNS:
                m = pat.search(block)
                if m:
                    date_text = m.group(0)
                    break
        return title, date_text, detail_url

    # Senate legacy CMS: div.element (Rick Scott, Grassley, etc.)
    if "element" in item.get("class", []) and item.select_one(".element-title"):
        title_el = item.select_one(".element-title")
        if title_el:
            title = title_el.get_text(strip=True)
        link_el = item.select_one("a[href]")
        if link_el:
            detail_url = urljoin(base_url, link_el.get("href", ""))
        date_el = item.select_one(".element-date")
        if date_el:
            date_text = date_el.get_text(strip=True)
        return title, date_text, detail_url

    # Title + link (generic)
    if item.name == "a":
        title = item.get_text(strip=True)
        href = item.get("href", "")
        if href:
            detail_url = urljoin(base_url, href)
    else:
        for tag in ["h2 a", "h3 a", "h4 a", "a"]:
            el = item.select_one(tag)
            if el and len(el.get_text(strip=True)) > 10:
                title = el.get_text(strip=True)
                href = el.get("href", "")
                if href and href != "#":
                    detail_url = urljoin(base_url, href)
                break
        if not title:
            for tag in ["h2", "h3", "h4", "td a"]:
                el = item.select_one(tag)
                if el and len(el.get_text(strip=True)) > 5:
                    title = el.get_text(strip=True)
                    if el.name == "a":
                        detail_url = urljoin(base_url, el.get("href", ""))
                    break

    # Date
    time_el = item.select_one("time") if item.name != "a" else None
    if time_el:
        date_text = time_el.get("datetime", "") or time_el.get_text(strip=True)
    else:
        for cls in ["date", "datetime", "timestamp", "ArticleBlock__date"]:
            el = item.select_one(f".{cls}")
            if el:
                date_text = el.get_text(strip=True)
                break
        if not date_text:
            block = item.get_text(" ", strip=True) if item.name != "a" else ""
            for pat, _ in DATE_PATTERNS:
                m = pat.search(block)
                if m:
                    date_text = m.group(0)
                    break

    return title, date_text, detail_url


def extract_body_text(soup):
    """Extract the main body text from a press release detail page."""
    # Try common content containers
    for sel in [
        "article .body", ".press-release-content", ".field-name-body",
        ".bodycopy", ".post-content", ".entry-content",
        "article .content", ".press_release__body",
        "#press-release-body", ".newsroom__press-release",
        "main article", "main .content",
    ]:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 100:
            return el.get_text("\n", strip=True)

    # Fallback: largest text block in main
    main = soup.select_one("main") or soup.select_one("article") or soup.body
    if not main:
        return ""

    # Find the div with the most paragraph text
    best = ""
    for div in main.find_all(["div", "section"]):
        paras = div.find_all("p")
        text = "\n".join(p.get_text(strip=True) for p in paras)
        if len(text) > len(best):
            best = text

    return best if len(best) > 100 else ""


def find_next_page(soup, current_url):
    """Find the next page URL from pagination."""
    # Next link
    for sel in ["a.next", "a[rel='next']", ".pagination a.next", "li.next a",
                 "a.pager-next", ".pager__item--next a"]:
        el = soup.select_one(sel)
        if el and el.get("href"):
            return urljoin(current_url, el["href"])

    # Page number links - find current and get next
    pager = soup.select_one(".pagination") or soup.select_one(".pager") or soup.select_one("nav[aria-label*='pagination' i]")
    if pager:
        active = pager.select_one(".active, .current, [aria-current]")
        if active:
            nxt = active.find_next_sibling()
            if nxt:
                link = nxt if nxt.name == "a" else nxt.select_one("a")
                if link and link.get("href"):
                    return urljoin(current_url, link["href"])

    return None


async def scrape_senator(client, semaphore, senator, run_id, max_pages, conn):
    """Scrape all press releases for one senator."""
    async with semaphore:
        sid = senator["id"]
        name = senator["full_name"]
        pr_url = senator["press_release_url"]
        config = senator.get("scrape_config", {}) or {}
        selectors = config.get("selectors", {})

        if not pr_url:
            print(f"  [!] {name}: no press_release_url, skipping")
            return 0, 0

        inserted = 0
        skipped = 0
        page = 0
        current_url = pr_url

        while current_url and page < max_pages:
            page += 1
            try:
                resp = await client.get(current_url)
                await asyncio.sleep(0.5)  # politeness
            except Exception as e:
                print(f"  [X] {name} page {page}: {type(e).__name__}")
                break

            if resp.status_code != 200:
                print(f"  [X] {name} page {page}: HTTP {resp.status_code}")
                break

            soup = BeautifulSoup(resp.text, "lxml")
            items = extract_listing_items(soup, selectors)

            if not items:
                break

            stop_pagination = False
            for item in items:
                title, date_text, detail_url = extract_item_data(item, str(resp.url), selectors)
                if not title or len(title) < 5:
                    continue

                pub_date = parse_date(date_text)

                # Stop if we've gone past the cutoff
                if pub_date and pub_date < CUTOFF_DATE:
                    stop_pagination = True
                    break

                # Skip if no detail URL
                if not detail_url:
                    continue

                # Check if already in DB
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM press_releases WHERE source_url = %s", (detail_url,))
                if cur.fetchone():
                    skipped += 1
                    cur.close()
                    continue
                cur.close()

                # Fetch detail page for body text
                body_text = ""
                try:
                    detail_resp = await client.get(detail_url)
                    await asyncio.sleep(0.3)
                    if detail_resp.status_code == 200:
                        detail_soup = BeautifulSoup(detail_resp.text, "lxml")
                        body_text = extract_body_text(detail_soup)
                except Exception:
                    pass

                # Insert
                cur = conn.cursor()
                try:
                    cur.execute("""
                        INSERT INTO press_releases (senator_id, title, published_at, body_text, source_url, scrape_run)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (source_url) DO NOTHING
                    """, (sid, title, pub_date, body_text or None, detail_url, run_id))
                    conn.commit()
                    if cur.rowcount > 0:
                        inserted += 1
                        date_str = pub_date.strftime("%Y-%m-%d") if pub_date else "no date"
                        print(f"    + {date_str} | {title[:70]}")
                except Exception as e:
                    conn.rollback()
                    print(f"    [ERR] {type(e).__name__}: {e}")
                finally:
                    cur.close()

            if stop_pagination:
                break

            # Find next page
            current_url = find_next_page(soup, str(resp.url))

        print(f"  [{'+' if inserted else '-'}] {name}: {inserted} inserted, {skipped} skipped, {page} pages")
        return inserted, skipped


async def main():
    parser = argparse.ArgumentParser(description="Capitol Releases backfill")
    parser.add_argument("--senators", nargs="*", help="Specific senator IDs to scrape")
    parser.add_argument("--limit", type=int, help="Limit to N senators (highest confidence first)")
    parser.add_argument("--max-pages", type=int, default=5, help="Max pages to paginate per senator")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # Load senators from DB
    if args.senators:
        placeholders = ",".join(["%s"] * len(args.senators))
        cur.execute(f"SELECT id, full_name, press_release_url, parser_family, scrape_config, confidence FROM senators WHERE id IN ({placeholders})", args.senators)
    else:
        cur.execute("SELECT id, full_name, press_release_url, parser_family, scrape_config, confidence FROM senators WHERE press_release_url IS NOT NULL ORDER BY confidence DESC")

    rows = cur.fetchall()
    if args.limit:
        rows = rows[:args.limit]

    senators = []
    for row in rows:
        senators.append({
            "id": row[0], "full_name": row[1], "press_release_url": row[2],
            "parser_family": row[3], "scrape_config": row[4], "confidence": row[5],
        })

    run_id = f"backfill-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"

    # Record run
    cur.execute("INSERT INTO scrape_runs (id, run_type) VALUES (%s, 'backfill')", (run_id,))
    conn.commit()
    cur.close()

    print(f"\n{'='*70}")
    print(f"  CAPITOL RELEASES BACKFILL")
    print(f"  Run: {run_id}")
    print(f"  Senators: {len(senators)}")
    print(f"  Max pages per senator: {args.max_pages}")
    print(f"  Cutoff: {CUTOFF_DATE.strftime('%Y-%m-%d')}")
    print(f"{'='*70}\n")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
        follow_redirects=True,
    ) as client:
        tasks = [scrape_senator(client, semaphore, s, run_id, args.max_pages, conn) for s in senators]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    total_inserted = 0
    total_skipped = 0
    errors = 0
    for r in results:
        if isinstance(r, Exception):
            errors += 1
        else:
            total_inserted += r[0]
            total_skipped += r[1]

    # Update run stats
    cur = conn.cursor()
    cur.execute("""
        UPDATE scrape_runs SET finished_at = NOW(), stats = %s WHERE id = %s
    """, (json.dumps({"inserted": total_inserted, "skipped": total_skipped, "errors": errors}), run_id))
    conn.commit()
    cur.close()
    conn.close()

    print(f"\n{'='*70}")
    print(f"  DONE: {total_inserted} inserted, {total_skipped} skipped, {errors} errors")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
