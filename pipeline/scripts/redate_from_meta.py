"""
Re-date existing records by re-fetching detail pages and reading
article:published_time meta tags. Targets records where the current
published_at is clearly a URL-path fallback (day=1 clumping).

Usage:
    python -m pipeline.scripts.redate_from_meta \\
        --senators scott-rick blackburn-marsha tillis-thom johnson-ron

    python -m pipeline.scripts.redate_from_meta --senators scott-rick --dry-run
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg2
from bs4 import BeautifulSoup

# Load .env
env_path = Path(__file__).resolve().parents[1] / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from pipeline.lib.dates import extract_date_from_html  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("redate")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


async def fetch_and_parse(
    client: httpx.AsyncClient,
    url: str,
    sem: asyncio.Semaphore,
    delay: float,
):
    async with sem:
        await asyncio.sleep(delay)
        try:
            resp = await client.get(url, follow_redirects=True, timeout=20.0)
            if resp.status_code != 200:
                return None, f"HTTP {resp.status_code}"
            soup = BeautifulSoup(resp.text, "lxml")
            dr = extract_date_from_html(soup)
            if dr:
                return dr, None
            return None, "no date found"
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"


async def process_senator(
    senator_id: str, conn, dry_run: bool, concurrency: int
) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, source_url, published_at, date_source, date_confidence
        FROM press_releases
        WHERE senator_id = %s
          AND deleted_at IS NULL
          AND published_at >= '2025-01-01'
          AND (
                date_source IS NULL
             OR date_source = 'url_path'
             OR date_confidence < 0.9
          )
        ORDER BY published_at
        """,
        (senator_id,),
    )
    rows = cur.fetchall()
    cur.close()

    stats = {
        "senator": senator_id,
        "candidates": len(rows),
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "errors": 0,
        "start": time.monotonic(),
    }

    if not rows:
        log.info("%s: no candidates", senator_id)
        return stats

    log.info("%s: %d candidates", senator_id, len(rows))

    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(headers=HEADERS) as client:
        tasks = [fetch_and_parse(client, row[1], sem) for row in rows]
        results = await asyncio.gather(*tasks)

    update_cur = conn.cursor()
    for row, (dr, err) in zip(rows, results):
        rec_id, url, cur_date, cur_source, cur_conf = row
        if dr is None:
            stats["errors"] += 1
            if stats["errors"] <= 3:
                log.warning("%s error: %s — %s", senator_id, url, err)
            continue

        new_date = dr.value.astimezone(timezone.utc)
        cur_date_utc = (
            cur_date.astimezone(timezone.utc) if cur_date else None
        )

        # Only update if date actually differs (day-level precision) OR
        # we got higher-confidence provenance
        date_day_changed = (
            cur_date_utc is None
            or cur_date_utc.date() != new_date.date()
        )
        conf_upgrade = (cur_conf or 0) < dr.confidence

        if not date_day_changed and not conf_upgrade:
            stats["unchanged"] += 1
            continue

        if date_day_changed:
            stats["updated"] += 1
        else:
            stats["skipped"] += 1

        if not dry_run:
            update_cur.execute(
                """
                UPDATE press_releases
                SET published_at = %s,
                    date_source = %s,
                    date_confidence = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (new_date, dr.source, dr.confidence, rec_id),
            )

    if not dry_run:
        conn.commit()
    update_cur.close()

    stats["elapsed"] = time.monotonic() - stats["start"]
    log.info(
        "%s done: candidates=%d updated=%d unchanged=%d errors=%d (%.1fs)",
        senator_id, stats["candidates"], stats["updated"],
        stats["unchanged"], stats["errors"], stats["elapsed"],
    )
    return stats


async def main_async(args):
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False

    all_stats = []
    for sid in args.senators:
        s = await process_senator(sid, conn, args.dry_run, args.concurrency)
        all_stats.append(s)

    conn.close()

    print("\n=== SUMMARY ===")
    print(f"{'senator':<22} {'cand':>5} {'updated':>8} {'unch':>5} {'err':>4}")
    for s in all_stats:
        print(
            f"{s['senator']:<22} {s['candidates']:>5} {s['updated']:>8} "
            f"{s['unchanged']:>5} {s['errors']:>4}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--senators",
        nargs="+",
        required=True,
        help="Senator IDs to re-date",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
