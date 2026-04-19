"""
Re-date existing records by walking the listing page's .element-datetime
spans (MM/DD/YYYY format). Much cheaper than refetching every detail
page — ~10 records per listing request.

For senate-legacy ".element" CMS sites. Known affected:
    scott-rick, blackburn-marsha, tillis-thom, johnson-ron.

Usage:
    python -m pipeline.scripts.redate_from_listing \\
        --senators scott-rick blackburn-marsha tillis-thom johnson-ron \\
        --max-pages 50
"""

import argparse
import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
import psycopg2
from bs4 import BeautifulSoup

env_path = Path(__file__).resolve().parents[1] / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("redate-listing")

HEADERS = {
    "User-Agent": (
        "CapitolReleases/1.0 (+trevorbrown.web@gmail.com) "
        "httpx/0.27"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MDY_RE = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})")
SHORT_DATE_RE = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2})",
    re.I,
)
URL_YEAR_RE = re.compile(r"/(\d{4})/")
MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_mdy(txt: str):
    if not txt:
        return None
    m = MDY_RE.search(txt)
    if not m:
        return None
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_short_date(txt: str, url: str):
    """'Apr 16' + URL '/2026/4/slug' => datetime(2026,4,16)."""
    if not txt or not url:
        return None
    m = SHORT_DATE_RE.search(txt)
    if not m:
        return None
    month = MONTH_MAP.get(m.group(1).lower()[:3])
    if not month:
        return None
    day = int(m.group(2))
    ym = URL_YEAR_RE.search(url)
    if not ym:
        return None
    year = int(ym.group(1))
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def normalize(url: str) -> str:
    """Strip fragment, trailing slash, and /index.php path prefix.

    Sites built on senate-legacy CMS sometimes expose URLs with and without
    /index.php/ — the same record. Treat them as equivalent.
    """
    u = url.split("#", 1)[0]
    u = u.replace("/index.php/", "/")
    return u.rstrip("/")


def extract_listing(soup, base_url: str):
    """Return list of (source_url, datetime) from listing page."""
    out = []
    for item in soup.select("div.element"):
        link = item.select_one("a[href]")
        if not link:
            continue
        href = urljoin(base_url, link.get("href", ""))
        date_el = (
            item.select_one(".element-datetime")
            or item.select_one(".element-date")
        )
        if not date_el:
            continue
        date_text = date_el.get_text(strip=True)
        # Newer template: "04/16/2026"; older template: "Apr 16" + URL year.
        dt = parse_mdy(date_text) or parse_short_date(date_text, href)
        if dt:
            out.append((href, dt))
    return out


async def fetch_listing(
    client: httpx.AsyncClient, base: str, page: int
):
    if page == 1:
        url = base
    else:
        sep = "&" if "?" in base else "?"
        url = f"{base}{sep}page={page}"
    try:
        resp = await client.get(url, follow_redirects=True, timeout=20.0)
        if resp.status_code != 200:
            return url, resp.status_code, []
        soup = BeautifulSoup(resp.text, "lxml")
        return url, 200, extract_listing(soup, url)
    except Exception as e:
        return url, f"ERR {type(e).__name__}: {e}", []


async def process_senator(senator_id: str, pr_url: str, conn, args):
    url_to_date: dict[str, datetime] = {}
    pages_ok = 0
    pages_empty = 0

    async with httpx.AsyncClient(headers=HEADERS) as client:
        for page in range(1, args.max_pages + 1):
            url, status, entries = await fetch_listing(client, pr_url, page)
            if status != 200:
                log.warning("%s page %d: status %s", senator_id, page, status)
                break
            if not entries:
                pages_empty += 1
                log.info("%s page %d: no entries, stopping", senator_id, page)
                break
            pages_ok += 1
            # Dedup-insert
            new_entries = 0
            for u, dt in entries:
                key = normalize(u)
                if key not in url_to_date:
                    url_to_date[key] = dt
                    new_entries += 1
            log.info(
                "%s page %d: %d entries (%d new, total=%d)",
                senator_id, page, len(entries), new_entries, len(url_to_date),
            )
            if new_entries == 0:
                # We've cycled; stop
                break
            await asyncio.sleep(args.delay)

    log.info("%s: walked %d pages, collected %d unique URLs",
             senator_id, pages_ok, len(url_to_date))

    if not url_to_date:
        return {"senator": senator_id, "collected": 0, "matched": 0,
                "updated": 0, "conflicts": 0}

    # Build map of DB records for this senator
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, source_url, published_at, date_source, date_confidence
        FROM press_releases
        WHERE senator_id = %s AND deleted_at IS NULL
        """,
        (senator_id,),
    )
    db_rows = cur.fetchall()
    cur.close()

    db_by_url = {normalize(r[1]): r for r in db_rows}

    matched = 0
    updated = 0
    conflicts = 0
    update_cur = conn.cursor()
    for key, dt in url_to_date.items():
        row = db_by_url.get(key)
        if not row:
            continue
        matched += 1
        rec_id, src_url, cur_date, cur_source, cur_conf = row
        cur_date_utc = cur_date.astimezone(timezone.utc) if cur_date else None
        day_changed = cur_date_utc is None or cur_date_utc.date() != dt.date()
        new_conf = 0.85
        new_source = "page_text"
        conf_upgrade = (cur_conf or 0) < new_conf

        if not day_changed and not conf_upgrade:
            continue

        if day_changed and cur_source == "meta_tag" and (cur_conf or 0) >= 0.9:
            # Listing date disagrees with previously-confirmed meta date — trust meta
            conflicts += 1
            continue

        updated += 1
        if not args.dry_run:
            update_cur.execute(
                """
                UPDATE press_releases
                SET published_at = %s,
                    date_source = %s,
                    date_confidence = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (dt, new_source, new_conf, rec_id),
            )

    if not args.dry_run:
        conn.commit()
    update_cur.close()

    return {"senator": senator_id, "collected": len(url_to_date),
            "matched": matched, "updated": updated, "conflicts": conflicts}


async def main_async(args):
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False

    # Fetch press_release_url for each senator
    cur = conn.cursor()
    sids = tuple(args.senators)
    cur.execute(
        "SELECT id, press_release_url FROM senators WHERE id IN %s",
        (sids,),
    )
    urls = dict(cur.fetchall())
    cur.close()

    all_stats = []
    for sid in args.senators:
        pr_url = urls.get(sid)
        if not pr_url:
            log.warning("%s: no press_release_url configured", sid)
            continue
        start = time.monotonic()
        s = await process_senator(sid, pr_url, conn, args)
        s["elapsed"] = time.monotonic() - start
        all_stats.append(s)

    conn.close()

    print("\n=== SUMMARY ===")
    print(f"{'senator':<22} {'collected':>10} {'matched':>8} {'updated':>8} {'conflicts':>10}")
    for s in all_stats:
        print(
            f"{s['senator']:<22} {s['collected']:>10} {s['matched']:>8} "
            f"{s['updated']:>8} {s['conflicts']:>10}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--senators", nargs="+", required=True)
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Delay between page fetches (seconds)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
