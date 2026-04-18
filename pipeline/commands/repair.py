"""
Capitol Releases -- Data Repair

Fixes null dates and missing body text by re-fetching detail pages
and extracting data using the unified date parsing library with
provenance tracking.

Usage:
    python -m pipeline.commands.repair dates                    # fix null dates
    python -m pipeline.commands.repair dates --senator king-angus
    python -m pipeline.commands.repair body                     # fix missing body text
    python -m pipeline.commands.repair body --senator young-todd
    python -m pipeline.commands.repair --dry-run dates
"""

import asyncio
import logging
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg2
from bs4 import BeautifulSoup

from pipeline.lib.dates import extract_date, extract_date_from_url, extract_date_from_html, parse_date_text
from pipeline.lib.http import create_client, fetch_with_retry, politeness_delay
from pipeline.lib.identity import content_hash

# Load .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.environ["DATABASE_URL"]
log = logging.getLogger("capitol.repair")


def get_null_date_records(conn, senator_id: str = None, limit: int = 1000) -> list[tuple]:
    """Get records with null published_at."""
    cur = conn.cursor()
    query = """
        SELECT id::text, senator_id, source_url, title
        FROM press_releases
        WHERE published_at IS NULL
        AND deleted_at IS NULL
    """
    params = []
    if senator_id:
        query += " AND senator_id = %s"
        params.append(senator_id)
    query += " ORDER BY senator_id, scraped_at DESC LIMIT %s"
    params.append(limit)
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def get_no_body_records(conn, senator_id: str = None, limit: int = 500) -> list[tuple]:
    """Get records with null or very short body text."""
    cur = conn.cursor()
    query = """
        SELECT id::text, senator_id, source_url, title
        FROM press_releases
        WHERE (body_text IS NULL OR length(body_text) < 50)
        AND deleted_at IS NULL
        AND source_url LIKE '%%senate.gov%%'
    """
    params = []
    if senator_id:
        query += " AND senator_id = %s"
        params.append(senator_id)
    query += " ORDER BY senator_id LIMIT %s"
    params.append(limit)
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return rows


async def repair_dates(
    records: list[tuple],
    conn,
    dry_run: bool = False,
    max_concurrent: int = 8,
) -> dict:
    """Repair null dates by re-fetching detail pages."""
    stats = {"total": len(records), "url_fixed": 0, "html_fixed": 0, "unfixable": 0, "errors": 0}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def repair_one(client, record_id, senator_id, source_url, title):
        async with semaphore:
            # Strategy 1: Extract from URL path
            url_result = extract_date_from_url(source_url)
            if url_result:
                if not dry_run:
                    cur = conn.cursor()
                    cur.execute("""
                        UPDATE press_releases
                        SET published_at = %s, date_source = %s, date_confidence = %s, updated_at = NOW()
                        WHERE id = %s::uuid
                    """, (url_result.value, url_result.source, url_result.confidence, record_id))
                    conn.commit()
                    cur.close()
                stats["url_fixed"] += 1
                log.info("URL fix: %s -> %s", source_url[:60], url_result.value.date())
                return

            # Strategy 2: Fetch detail page and extract from HTML
            try:
                resp = await fetch_with_retry(client, source_url)
                await politeness_delay(0.3)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    html_result = extract_date_from_html(soup)
                    if html_result:
                        if not dry_run:
                            cur = conn.cursor()
                            cur.execute("""
                                UPDATE press_releases
                                SET published_at = %s, date_source = %s, date_confidence = %s, updated_at = NOW()
                                WHERE id = %s::uuid
                            """, (html_result.value, html_result.source, html_result.confidence, record_id))
                            conn.commit()
                            cur.close()
                        stats["html_fixed"] += 1
                        log.info("HTML fix: %s -> %s (via %s)", source_url[:60], html_result.value.date(), html_result.source)
                        return
                elif resp.status_code in (404, 410):
                    # Page is gone -- mark as deleted
                    if not dry_run:
                        cur = conn.cursor()
                        cur.execute("UPDATE press_releases SET deleted_at = NOW() WHERE id = %s::uuid", (record_id,))
                        conn.commit()
                        cur.close()
                    log.info("DELETED: %s returned %d", source_url[:60], resp.status_code)
                    return
            except Exception as e:
                log.warning("Fetch failed for %s: %s", source_url[:60], e)
                stats["errors"] += 1
                return

            stats["unfixable"] += 1

    async with create_client(timeout=15.0) as client:
        tasks = [repair_one(client, *record) for record in records]
        await asyncio.gather(*tasks)

    return stats


async def repair_body_text(
    records: list[tuple],
    conn,
    dry_run: bool = False,
    max_concurrent: int = 6,
) -> dict:
    """Repair missing body text by re-fetching detail pages."""
    stats = {"total": len(records), "fixed": 0, "unfixable": 0, "errors": 0}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def repair_one(client, record_id, senator_id, source_url, title):
        async with semaphore:
            try:
                resp = await fetch_with_retry(client, source_url)
                await politeness_delay(0.3)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    body = _extract_body(soup)
                    if body and len(body) > 50:
                        if not dry_run:
                            cur = conn.cursor()
                            cur.execute("""
                                UPDATE press_releases
                                SET body_text = %s, raw_html = %s,
                                    content_hash = %s, updated_at = NOW()
                                WHERE id = %s::uuid
                            """, (body, resp.text, content_hash(body), record_id))
                            conn.commit()
                            cur.close()
                        stats["fixed"] += 1
                        log.info("Body fixed: %s (%d chars)", title[:50], len(body))
                        return
            except Exception as e:
                log.warning("Fetch failed for %s: %s", source_url[:60], e)
                stats["errors"] += 1
                return
            stats["unfixable"] += 1

    async with create_client(timeout=15.0) as client:
        tasks = [repair_one(client, *record) for record in records]
        await asyncio.gather(*tasks)

    return stats


def _extract_body(soup):
    """Extract body text from a detail page."""
    for sel in [
        "article .entry-content", ".post-content", ".field-name-body",
        ".bodycopy", "article .content", ".press_release__body",
        "#press-release-body", ".newsroom__press-release",
        "main article", "main .content", ".Heading--body",
    ]:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 100:
            return el.get_text("\n", strip=True)

    main = soup.select_one("main") or soup.select_one("article") or soup.body
    if not main:
        return ""
    best = ""
    for div in main.find_all(["div", "section"]):
        paras = div.find_all("p")
        text = "\n".join(p.get_text(strip=True) for p in paras)
        if len(text) > len(best):
            best = text
    return best if len(best) > 100 else ""


def main():
    parser = argparse.ArgumentParser(description="Capitol Releases data repair")
    parser.add_argument("mode", choices=["dates", "body"], help="What to repair")
    parser.add_argument("--senator", help="Only repair specific senator")
    parser.add_argument("--limit", type=int, default=1000, help="Max records to repair")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    conn = psycopg2.connect(DB_URL)

    if args.mode == "dates":
        records = get_null_date_records(conn, args.senator, args.limit)
        log.info("Found %d records with null dates", len(records))
        if records:
            stats = asyncio.run(repair_dates(records, conn, args.dry_run))
            print(f"\nDate repair: {stats['url_fixed']} from URL, {stats['html_fixed']} from HTML, "
                  f"{stats['unfixable']} unfixable, {stats['errors']} errors (of {stats['total']} total)")
        else:
            print("No records need date repair")
    elif args.mode == "body":
        records = get_no_body_records(conn, args.senator, args.limit)
        log.info("Found %d records with missing body text", len(records))
        if records:
            stats = asyncio.run(repair_body_text(records, conn, args.dry_run))
            print(f"\nBody repair: {stats['fixed']} fixed, {stats['unfixable']} unfixable, "
                  f"{stats['errors']} errors (of {stats['total']} total)")
        else:
            print("No records need body repair")

    conn.close()


if __name__ == "__main__":
    main()
