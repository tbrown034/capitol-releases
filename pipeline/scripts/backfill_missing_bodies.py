"""
Fill body_text for rows that were stored with title + URL only.

Root cause: the silo / WP-extras / op-ed backfill paths insert straight
from the listing page and never fetch the detail page, so every row they
create has an empty body. `backfill_silos.py` even imports
`extract_body_text` without calling it. That accounts for 2,557 of the
~3,200 bodyless live rows (100% of `silo-*` runs), and it is why the
newsletter, weekly-column, blog and floor-statement content types have
far worse body coverage than press releases.

This script is the repair half. It re-fetches each bodyless row's
source_url, extracts the body with the same `extract_body_text` the
daily collector uses, and writes body_text plus content_hash. Rows whose
page no longer serves a body are left alone and reported, never deleted.

Setting content_hash here establishes the change-detection baseline for
these rows, which they never had.

Usage:
    python -m pipeline.scripts.backfill_missing_bodies --dry-run
    python -m pipeline.scripts.backfill_missing_bodies --apply --limit 200
    python -m pipeline.scripts.backfill_missing_bodies --apply \\
        --officials grassley-chuck nunn-zachary

Re-runnable: repaired rows fall out of the candidate query.
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

import httpx
import psycopg2
from bs4 import BeautifulSoup

for _name in (".env.local", ".env"):
    _path = Path(__file__).resolve().parents[2] / _name
    if _path.exists():
        for _line in _path.read_text().splitlines():
            if _line.strip() and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from pipeline.backfill import extract_body_text  # noqa: E402
from pipeline.lib.identity import content_hash  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("backfill_bodies")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Upgrade-Insecure-Requests": "1",
}

CANDIDATE_SQL = """
    SELECT id, official_id, source_url, content_type
    FROM press_releases
    WHERE deleted_at IS NULL
      AND coalesce(body_text, '') = ''
    ORDER BY official_id, published_at DESC NULLS LAST
"""

# Below this a "body" is almost certainly nav chrome or a cookie banner
# rather than real content, so the row is left bodyless and reported.
MIN_BODY_CHARS = 200


async def fetch_body(client, url, sem, delay):
    async with sem:
        await asyncio.sleep(delay)
        try:
            resp = await client.get(url, follow_redirects=True, timeout=25.0)
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"
        body = extract_body_text(BeautifulSoup(resp.text, "lxml"))
        if not body or len(body) < MIN_BODY_CHARS:
            return None, f"body too short ({len(body or '')} chars)"
        return body, None


async def run(conn, rows, args):
    log.info("%d bodyless rows to attempt", len(rows))
    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(headers=HEADERS) as client:
        results = await asyncio.gather(
            *(fetch_body(client, r[2], sem, args.delay) for r in rows)
        )

    planned, failures = [], []
    for (rec_id, oid, url, ctype), (body, err) in zip(rows, results):
        if body is None:
            failures.append((oid, ctype, err, url))
        else:
            planned.append((rec_id, oid, ctype, url, body))

    by_official = {}
    for _id, oid, ctype, _url, body in planned:
        entry = by_official.setdefault(oid, {"n": 0, "chars": 0})
        entry["n"] += 1
        entry["chars"] += len(body)

    print(f"\n=== bodies recovered for {len(planned)} rows "
          f"({len(failures)} could not be recovered) ===")
    print(f"{'official':<24} {'rows':>5} {'avg chars':>10}")
    for oid, e in sorted(by_official.items(), key=lambda kv: -kv[1]["n"]):
        print(f"{oid:<24} {e['n']:>5} {e['chars'] // max(e['n'], 1):>10}")

    if failures:
        reasons = {}
        for _oid, _ct, err, _url in failures:
            key = err.split(" (")[0].split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1
        print("\n--- unrecovered, grouped by reason (rows left untouched) ---")
        for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"  {k:<34} {v}")

    if not args.apply:
        print("\n[dry-run] no changes written")
        return 0

    # Fetching thousands of detail pages takes minutes, and Neon drops the
    # idle session in the meantime, so reconnect before writing.
    try:
        conn.close()
    except Exception:
        pass
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    cur = conn.cursor()
    cur.executemany(
        """
        UPDATE press_releases
        SET body_text = %s, content_hash = %s, updated_at = now()
        WHERE id = %s
        """,
        [(body, content_hash(body), rec_id)
         for rec_id, _oid, _ct, _url, body in planned],
    )
    conn.commit()
    cur.close()
    print(f"\nfilled {len(planned)} bodies")
    return len(planned)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Write changes. Without it only the plan prints.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--officials", nargs="*")
    parser.add_argument("--content-types", nargs="*")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()
    if args.dry_run:
        args.apply = False

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(CANDIDATE_SQL)
    rows = cur.fetchall()
    cur.close()

    if args.officials:
        rows = [r for r in rows if r[1] in set(args.officials)]
    if args.content_types:
        rows = [r for r in rows if r[3] in set(args.content_types)]
    if args.limit:
        rows = rows[: args.limit]

    if not rows:
        print("no bodyless rows match")
        conn.close()
        return

    started = time.monotonic()
    filled = asyncio.run(run(conn, rows, args))
    conn.close()
    print(f"done: {filled} rows filled in {time.monotonic() - started:.1f}s")


if __name__ == "__main__":
    sys.exit(main())
