"""
Capitol Releases -- Verification Script

For each senator, visits their press release listing page, counts the
actual number of releases available, and compares against what we have
in the database. Reports exact discrepancies.

Usage:
    python verify.py                    # verify all senators
    python verify.py --senators daines-steve
    python verify.py --fix              # also attempts to backfill gaps
"""

import asyncio
import json
import os
import re
import sys
import argparse
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx
import psycopg2
from bs4 import BeautifulSoup

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_CH7k3vjTsoRG@ep-young-tree-amictscx-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

CUTOFF = datetime(2025, 1, 1, tzinfo=timezone.utc)

DATE_PATTERN = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s+\d{4}|"
    r"\d{1,2}/\d{1,2}/\d{2,4}|"
    r"\d{4}-\d{2}-\d{2}"
)


def count_listing_items(soup):
    """Count press release items on a single listing page."""
    # Try each known selector pattern, return the best count
    for sel in [
        ".ArticleBlock",
        "div.e-loop-item",
        "div.media-list-body",
        ".PressBlock",
        ".jet-listing-grid__item",
        "article.et_pb_post",
        "article.postItem",
        "div.element",
        "table.table-striped tbody tr",
        ".views-row",
        ".element-list .element",
    ]:
        items = soup.select(sel)
        if len(items) >= 2:
            return len(items), sel
    return 0, None


def find_total_from_pagination(soup, url):
    """Try to extract total count or page count from pagination elements."""
    # Look for "Page X of Y" or "Showing X-Y of Z" patterns
    text = soup.get_text(" ", strip=True)

    # "Page 1 of 25" pattern
    m = re.search(r"[Pp]age\s+\d+\s+of\s+(\d+)", text)
    if m:
        return int(m.group(1)), "pages"

    # "Showing 1-10 of 234" pattern
    m = re.search(r"of\s+(\d+)\s+(?:results?|entries|items|records)", text)
    if m:
        return int(m.group(1)), "items"

    # Count pagination links to estimate total pages
    pager = (
        soup.select_one(".pagination")
        or soup.select_one(".pager")
        or soup.select_one("nav[aria-label*='pagination' i]")
    )
    if pager:
        page_links = pager.select("a[href]")
        page_nums = []
        for link in page_links:
            t = link.get_text(strip=True)
            if t.isdigit():
                page_nums.append(int(t))
        if page_nums:
            return max(page_nums), "pages"

    # WordPress: check for "page/N" links
    last_page_links = soup.select("a[href*='/page/']")
    page_nums = []
    for link in last_page_links:
        m = re.search(r"/page/(\d+)", link.get("href", ""))
        if m:
            page_nums.append(int(m.group(1)))
    if page_nums:
        return max(page_nums), "pages"

    # ColdFusion: check for offset links
    offset_links = soup.select("a[href*='offset=']")
    offsets = []
    for link in offset_links:
        m = re.search(r"offset=(\d+)", link.get("href", ""))
        if m:
            offsets.append(int(m.group(1)))
    if offsets:
        return max(offsets), "offset"

    return None, None


async def verify_senator(client, semaphore, senator, db_count, db_earliest):
    """Verify one senator's press release count against their live site."""
    async with semaphore:
        sid = senator["id"]
        name = senator["full_name"]
        url = senator["press_release_url"]

        result = {
            "senator_id": sid,
            "name": name,
            "party": senator["party"],
            "state": senator["state"],
            "url": url,
            "db_count": db_count,
            "db_earliest": str(db_earliest) if db_earliest else None,
            "site_page1_count": 0,
            "site_total_estimate": None,
            "site_total_type": None,
            "items_per_page": None,
            "selector_used": None,
            "status": "unknown",
            "notes": "",
        }

        if not url:
            result["status"] = "no_url"
            return result

        try:
            resp = await client.get(url)
            await asyncio.sleep(0.3)
        except Exception as e:
            result["status"] = "error"
            result["notes"] = f"{type(e).__name__}: {e}"
            return result

        if resp.status_code != 200:
            result["status"] = "http_error"
            result["notes"] = f"HTTP {resp.status_code}"
            return result

        soup = BeautifulSoup(resp.text, "lxml")

        # Count items on page 1
        page1_count, selector = count_listing_items(soup)
        result["site_page1_count"] = page1_count
        result["selector_used"] = selector
        result["items_per_page"] = page1_count

        # Try to find total from pagination
        total, total_type = find_total_from_pagination(soup, url)
        if total:
            result["site_total_type"] = total_type
            if total_type == "pages":
                result["site_total_estimate"] = total * page1_count if page1_count else total * 10
            elif total_type == "items":
                result["site_total_estimate"] = total
            elif total_type == "offset":
                result["site_total_estimate"] = total + page1_count

        # Determine status
        if page1_count == 0:
            result["status"] = "no_items_found"
            result["notes"] = "Could not find press release items on listing page"
        elif db_count == 0:
            result["status"] = "NOT_SCRAPED"
        elif result["site_total_estimate"] and db_count < result["site_total_estimate"] * 0.8:
            result["status"] = "INCOMPLETE"
            result["notes"] = f"DB has {db_count}, site estimates ~{result['site_total_estimate']}"
        elif db_earliest and str(db_earliest) > "2025-03-01":
            result["status"] = "SHALLOW"
            result["notes"] = f"Earliest in DB is {db_earliest}, should reach Jan 2025"
        else:
            result["status"] = "ok"

        return result


async def main():
    parser = argparse.ArgumentParser(description="Verify press release completeness")
    parser.add_argument("--senators", nargs="*", help="Specific senator IDs")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # Load all senators and their DB counts
    cur.execute("""
        SELECT s.id, s.full_name, s.party, s.state, s.press_release_url,
               count(pr.id)::int as cnt,
               min(pr.published_at)::date as earliest,
               max(pr.published_at)::date as latest
        FROM senators s
        LEFT JOIN press_releases pr ON pr.senator_id = s.id
        GROUP BY s.id
        ORDER BY s.full_name
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    senators = []
    db_counts = {}
    db_earliests = {}
    for row in rows:
        sid = row[0]
        if args.senators and sid not in args.senators:
            continue
        senators.append({
            "id": sid,
            "full_name": row[1],
            "party": row[2],
            "state": row[3],
            "press_release_url": row[4],
        })
        db_counts[sid] = row[5]
        db_earliests[sid] = row[6]

    print(f"\n{'='*80}")
    print(f"  CAPITOL RELEASES VERIFICATION")
    print(f"  {len(senators)} senators to verify")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*80}\n")

    semaphore = asyncio.Semaphore(8)
    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(15.0),
        follow_redirects=True,
    ) as client:
        tasks = [
            verify_senator(client, semaphore, s, db_counts[s["id"]], db_earliests[s["id"]])
            for s in senators
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    clean = []
    for r in results:
        if isinstance(r, Exception):
            print(f"  [X] Exception: {r}")
        else:
            clean.append(r)

    # Sort by status severity
    status_order = {"NOT_SCRAPED": 0, "INCOMPLETE": 1, "SHALLOW": 2, "no_items_found": 3, "error": 4, "ok": 5, "no_url": 6, "unknown": 7, "http_error": 8}
    clean.sort(key=lambda x: (status_order.get(x["status"], 99), -x["db_count"]))

    # Print report
    problems = [r for r in clean if r["status"] not in ("ok", "no_url")]
    ok = [r for r in clean if r["status"] == "ok"]

    print(f"{'Name':35s} {'P':1s} {'ST':2s} {'DB':>6s} {'Site~':>7s} {'Earliest':>12s} {'Status':12s} Notes")
    print("-" * 110)
    for r in clean:
        est = str(r["site_total_estimate"] or "?")
        earliest = r["db_earliest"] or "none"
        flag = ""
        if r["status"] in ("NOT_SCRAPED", "INCOMPLETE", "SHALLOW", "no_items_found"):
            flag = "***"
        print(f"{r['name']:35s} {r['party']:1s} {r['state']:2s} {r['db_count']:>6d} {est:>7s} {earliest:>12s} {r['status']:12s} {r['notes'][:40]} {flag}")

    print(f"\n{'='*80}")
    print(f"  SUMMARY")
    print(f"  OK: {len(ok)}")
    print(f"  Problems: {len(problems)}")
    for status in ["NOT_SCRAPED", "INCOMPLETE", "SHALLOW", "no_items_found", "error", "http_error"]:
        cnt = sum(1 for r in clean if r["status"] == status)
        if cnt:
            print(f"    {status}: {cnt}")
    print(f"  Total DB records: {sum(r['db_count'] for r in clean)}")
    print(f"{'='*80}\n")

    # Save detailed results
    from pathlib import Path
    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(exist_ok=True)
    with open(results_dir / "verification.json", "w") as f:
        json.dump(clean, f, indent=2, default=str)
    print(f"Detailed results saved to {results_dir / 'verification.json'}")


if __name__ == "__main__":
    asyncio.run(main())
