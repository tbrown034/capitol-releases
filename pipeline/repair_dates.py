"""
Capitol Releases -- Date Repair Script

Fixes null published_at values by:
1. Extracting dates from the source URL path (/YYYY/M/ or /YYYY/MM/DD/)
2. Fetching the detail page and extracting dates from meta tags, time elements, or text
3. Flagging bad URLs (non-senate.gov, social media links, etc.)

Usage:
    python repair_dates.py                  # repair all null-date records
    python repair_dates.py --dry-run        # show what would be fixed without writing
    python repair_dates.py --senator cruz-ted
"""

import asyncio
import re
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import psycopg2
from bs4 import BeautifulSoup

# Load .env file if present
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.environ["DATABASE_URL"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def extract_date_from_url(url: str):
    """Try to extract a date from the URL path. Returns datetime or None."""
    # Pattern: /YYYY/MM/DD/
    m = re.search(r"/(\d{4})/(\d{1,2})/(\d{1,2})/", url)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            pass

    # Pattern: /YYYY/M/ (no day)
    m = re.search(r"/(\d{4})/(\d{1,2})/(?!\d)", url)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), 1, tzinfo=timezone.utc)
        except ValueError:
            pass

    # Pattern: /MM/DD/YYYY/ in URL
    m = re.search(r"/(\d{2})/(\d{2})/(\d{4})/", url)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def extract_date_from_html(html: str, soup: BeautifulSoup):
    """Extract publication date from a detail page."""
    # 1. OpenGraph / meta tags (most reliable)
    for attr in ["article:published_time", "og:article:published_time", "datePublished"]:
        meta = soup.find("meta", property=attr) or soup.find("meta", attrs={"name": attr})
        if meta and meta.get("content"):
            try:
                dt = datetime.fromisoformat(meta["content"].replace("Z", "+00:00"))
                return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
            except (ValueError, TypeError):
                pass

    # 2. JSON-LD
    for script in soup.select("script[type='application/ld+json']"):
        text = script.get_text()
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', text)
        if m:
            try:
                dt = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
                return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
            except (ValueError, TypeError):
                pass

    # 3. <time> element with datetime attribute
    time_el = soup.select_one("time[datetime]")
    if time_el:
        try:
            dt = datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except (ValueError, TypeError):
            pass

    # 4. <time> element with text
    time_el = soup.select_one("time")
    if time_el:
        return _parse_date_text(time_el.get_text(strip=True))

    # 5. Date-like text in common containers
    for sel in [".date", ".post-date", ".entry-date", ".published",
                ".ArticleBlock__date", ".press-release-date",
                ".field-name-field-date", ".post-media-list-date",
                "span.datetime"]:
        el = soup.select_one(sel)
        if el:
            return _parse_date_text(el.get_text(strip=True))

    # 6. Date in the first 500 chars of body text (header area)
    body = soup.select_one("main") or soup.select_one("article") or soup.body
    if body:
        text = body.get_text(" ", strip=True)[:500]
        return _parse_date_text(text)

    return None


def _parse_date_text(text: str):
    """Parse a date from text. Returns datetime or None."""
    if not text:
        return None

    # "April 15, 2026" or "Apr 15, 2026"
    m = re.search(r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*)\s+(\d{1,2}),?\s+(\d{4})", text, re.I)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(2)), tzinfo=timezone.utc)
            except ValueError:
                pass

    # "04/15/2026" or "4/15/26"
    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})", text)
    if m:
        try:
            year = int(m.group(3))
            if year < 100:
                year += 2000
            return datetime(year, int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc)
        except ValueError:
            pass

    # "2026-04-15"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def is_bad_url(url: str) -> str | None:
    """Check if a URL is not a real press release. Returns reason or None."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    if "senate.gov" not in domain and "house.gov" not in domain:
        return f"non-government domain: {domain}"
    if "bsky.app" in domain or "twitter.com" in domain or "facebook.com" in domain:
        return f"social media: {domain}"
    if url.endswith("/press-releases") or url.endswith("/press-releases/"):
        return "listing page URL, not a detail page"
    if "#" in url and url.index("#") < len(url) - 1:
        path_part = url.split("#")[0]
        if path_part.endswith("/press-releases") or path_part.endswith("/press-releases/"):
            return "listing page with anchor"

    return None


async def repair_batch(client, records, dry_run=False):
    """Repair dates for a batch of records."""
    stats = {"url_fixed": 0, "html_fixed": 0, "bad_url": 0, "unfixable": 0, "already_ok": 0}

    conn = psycopg2.connect(DB_URL) if not dry_run else None

    for record_id, source_url, senator_id, title in records:
        # Check for bad URLs first
        bad_reason = is_bad_url(source_url)
        if bad_reason:
            stats["bad_url"] += 1
            if not dry_run and conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM press_releases WHERE id = %s", (record_id,))
                conn.commit()
                cur.close()
            continue

        # Try URL-based date extraction
        url_date = extract_date_from_url(source_url)
        if url_date:
            stats["url_fixed"] += 1
            if not dry_run and conn:
                cur = conn.cursor()
                cur.execute("UPDATE press_releases SET published_at = %s WHERE id = %s", (url_date, record_id))
                conn.commit()
                cur.close()
            continue

        # Fetch the detail page
        try:
            resp = await client.get(source_url)
            await asyncio.sleep(0.3)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                html_date = extract_date_from_html(resp.text, soup)
                if html_date:
                    stats["html_fixed"] += 1
                    if not dry_run and conn:
                        cur = conn.cursor()
                        cur.execute("UPDATE press_releases SET published_at = %s WHERE id = %s", (html_date, record_id))
                        conn.commit()
                        cur.close()
                    continue
        except Exception:
            pass

        stats["unfixable"] += 1

    if conn:
        conn.close()

    return stats


async def main():
    parser = argparse.ArgumentParser(description="Repair null dates")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fixed")
    parser.add_argument("--senator", help="Specific senator ID")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    where = "WHERE pr.published_at IS NULL"
    params = []
    if args.senator:
        where += " AND pr.senator_id = %s"
        params.append(args.senator)

    cur.execute(f"""
        SELECT pr.id, pr.source_url, pr.senator_id, pr.title
        FROM press_releases pr
        {where}
        ORDER BY pr.senator_id, pr.scraped_at
    """, params)
    records = cur.fetchall()
    cur.close()
    conn.close()

    total = len(records)
    print(f"\n{'='*70}")
    print(f"  DATE REPAIR {'(DRY RUN)' if args.dry_run else ''}")
    print(f"  {total} records with null dates")
    print(f"{'='*70}\n")

    if total == 0:
        print("  Nothing to repair.")
        return

    # Process in batches
    all_stats = {"url_fixed": 0, "html_fixed": 0, "bad_url": 0, "unfixable": 0}
    batch_size = args.batch_size

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(15.0),
        follow_redirects=True,
    ) as client:
        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            stats = await repair_batch(client, batch, dry_run=args.dry_run)
            for k in all_stats:
                all_stats[k] += stats[k]

            done = min(i + batch_size, total)
            pct = done * 100 // total
            print(f"  [{pct:3d}%] {done}/{total}  url={all_stats['url_fixed']} html={all_stats['html_fixed']} bad={all_stats['bad_url']} unfixable={all_stats['unfixable']}")

    print(f"\n{'='*70}")
    print(f"  RESULTS:")
    print(f"    Fixed from URL path:    {all_stats['url_fixed']}")
    print(f"    Fixed from detail page: {all_stats['html_fixed']}")
    print(f"    Bad URLs removed:       {all_stats['bad_url']}")
    print(f"    Unfixable:              {all_stats['unfixable']}")
    print(f"    Total processed:        {total}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
