"""
Repair press_releases rows whose published_at came from a broken
extraction path, and tombstone rows that were never press releases.

Five anomaly classes, each selectable with --mode:

  clumped       Rows sharing one date because backfill's _nearby_date_text
                climbed into the wrapper holding every card on the listing
                page, so all ~20 rows inherited the newest item's date.
                Signature: date_source='listing_page' with >= --min-clump
                rows on the same (official_id, day).

  out-of-range  Rows dated before --window-start or in the future. Causes
                seen: the House documentsingle.aspx template hardcodes
                datetime="2017-11-13" on every <time>, and its
                article:published_time is a site-level value rather than
                the article's.

  null-date     Rows that never got a published_at. Concentrated in the
                senate.gov ColdFusion cohort, where the date lives in page
                text rather than markup; the body-text fallback in
                extract_date_from_html can usually recover it.

  dateless-junk Rows with no date whose URL is not article-shaped:
                nav menus scraped as releases (issue pages, flag
                requests, office locations, committee assignments).
                Tombstoned, not re-dated.

  nav-junk      Rows whose source_url is an office-locator / contact /
                biography page admitted before the nav denylist landed
                (backfill 254d2c4, daily collector 2279eb1). These are not
                collectable content, so they are tombstoned via deleted_at
                rather than re-dated. Nothing is ever hard-deleted.

The first two modes re-fetch the detail page and re-run
extract_date_from_html, which now skips related-news rails and
self-contradicting <time> elements. A row is only rewritten when the
freshly extracted date is plausible and actually differs.

This exists because the update.py upsert preserves first-touch
date_source / date_confidence / published_at forever — a bad date already
in the database never self-heals on re-collection, so the parser fix alone
does not clean history.

Usage:
    python -m pipeline.scripts.repair_bad_dates --mode clumped --dry-run
    python -m pipeline.scripts.repair_bad_dates --mode clumped --apply
    python -m pipeline.scripts.repair_bad_dates --mode out-of-range --apply
    python -m pipeline.scripts.repair_bad_dates --mode null-date --apply
    python -m pipeline.scripts.repair_bad_dates --mode dateless-junk --apply
    python -m pipeline.scripts.repair_bad_dates --mode nav-junk --apply

Re-runnable: rows already repaired fall out of the candidate query.
"""

import argparse
import asyncio
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg2
from bs4 import BeautifulSoup

# Load .env the same way the sibling repair scripts do. Quotes are stripped
# to match rag_embed.py: values in .env.local are written quoted, and a
# retained quote is carried straight into the value. That cost a day once
# already -- a quoted OPENAI_API_KEY produced 401s that looked like a bad
# key (2026-07-30) -- and here it makes psycopg2 reject the DSN outright.
for _name in (".env.local", ".env"):
    _path = Path(__file__).resolve().parents[2] / _name
    if _path.exists():
        for _line in _path.read_text().splitlines():
            if _line.strip() and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from pipeline.backfill import (  # noqa: E402
    _NAV_JUNK_PATH_FRAGMENTS,
    _is_external_detail_url,
)
from pipeline.lib.classifier import looks_like_article_url  # noqa: E402
from pipeline.lib.dates import (  # noqa: E402
    extract_date_from_html,
    is_plausible_date,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("repair_dates")

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
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

CLUMPED_SQL = """
    SELECT id, official_id, source_url, published_at, date_source,
           date_confidence, title
    FROM (
        SELECT id, official_id, source_url, published_at, date_source,
               date_confidence, title,
               count(*) OVER (
                   PARTITION BY official_id, published_at::date, date_source
               ) AS clump
        FROM press_releases
        WHERE deleted_at IS NULL
          AND published_at IS NOT NULL
          AND date_source = ANY(%s)
    ) s
    WHERE clump >= %s
    ORDER BY official_id, published_at
"""

OUT_OF_RANGE_SQL = """
    SELECT id, official_id, source_url, published_at, date_source,
           date_confidence, title
    FROM press_releases
    WHERE deleted_at IS NULL
      AND published_at IS NOT NULL
      AND (published_at < %s OR published_at > now() + interval '2 days')
    ORDER BY official_id, published_at
"""

NULL_DATE_SQL = """
    SELECT id, official_id, source_url, published_at, date_source,
           date_confidence, title
    FROM press_releases
    WHERE deleted_at IS NULL
      AND published_at IS NULL
    ORDER BY official_id
"""

# Prefilter in SQL on the denylist fragments so the scan does not pull the
# whole live corpus over the wire; _is_external_detail_url still has the
# final say on every row this returns.
NAV_JUNK_SQL = """
    SELECT id, official_id, source_url, published_at, date_source,
           date_confidence, title
    FROM press_releases
    WHERE deleted_at IS NULL
      AND source_url ~* %s
    ORDER BY official_id, source_url
"""


_WORD_PAT = re.compile(r"[a-z0-9]+")

def _page_still_shows_article(soup, stored_title: str) -> bool:
    """True if the fetched page is still the article we stored.

    A dead `documentsingle.aspx?documentid=` URL that now serves the
    press-release listing still carries an `article:published_time`, but it
    belongs to the listing rather than the article — trusting it would
    stamp a confident date that describes nothing. Compare the stored
    headline against the page's own headings and require real overlap
    before believing any date the page reports.

    Headings are read from og:title plus h1 *and* h2: the House ASPX
    template puts the section label ("news", "Press Releases") in the h1
    and the actual headline in an h2, so an h1-only check rejects every
    article on those sites.
    """
    if not stored_title:
        return True
    parts = []
    og = soup.select_one('meta[property="og:title"]')
    if og and og.get("content"):
        parts.append(og["content"])
    parts += [h.get_text(" ", strip=True) for h in soup.select("h1, h2")]
    heading = " ".join(parts)
    stored_words = set(_WORD_PAT.findall(stored_title.lower()))
    page_words = set(_WORD_PAT.findall(heading.lower()))
    stored_words -= _TITLE_STOPWORDS
    if not stored_words:
        return True
    return len(stored_words & page_words) / len(stored_words) >= 0.4


_TITLE_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "at",
    "with", "by", "from", "as", "is", "s", "rep", "sen", "congressman",
    "congresswoman", "senator", "press", "release", "releases", "news",
}


async def refetch_date(client, url, sem, delay, stored_title=""):
    """Re-fetch a detail page and re-extract its date with the fixed parser."""
    async with sem:
        await asyncio.sleep(delay)
        try:
            resp = await client.get(url, follow_redirects=True, timeout=25.0)
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"
        soup = BeautifulSoup(resp.text, "lxml")
        if not _page_still_shows_article(soup, stored_title):
            return None, "article no longer resolves (page serves listing)"
        result = extract_date_from_html(soup)
        if result is None:
            return None, "no date found"
        return result, None


def reconnect(conn):
    """Return a live connection, replacing one the server may have dropped."""
    try:
        conn.close()
    except Exception:
        pass
    fresh = psycopg2.connect(os.environ["DATABASE_URL"])
    fresh.autocommit = False
    return fresh


def select_candidates(conn, args):
    cur = conn.cursor()
    if args.mode == "clumped":
        cur.execute(CLUMPED_SQL, (args.date_sources, args.min_clump))
        rows = cur.fetchall()
    elif args.mode == "out-of-range":
        cur.execute(OUT_OF_RANGE_SQL, (args.window_start,))
        rows = cur.fetchall()
    elif args.mode == "null-date":
        # Dateless rows that still look like real articles get re-dated;
        # the navigation majority is handled by --mode dateless-junk.
        cur.execute(NULL_DATE_SQL)
        rows = [r for r in cur.fetchall() if looks_like_article_url(r[2])]
    elif args.mode == "dateless-junk":
        cur.execute(NULL_DATE_SQL)
        rows = [r for r in cur.fetchall() if not looks_like_article_url(r[2])]
    else:
        pattern = "|".join(re.escape(f) for f in _NAV_JUNK_PATH_FRAGMENTS)
        cur.execute(NAV_JUNK_SQL, (pattern,))
        rows = [r for r in cur.fetchall() if _is_external_detail_url(r[2])]
    cur.close()
    if args.officials:
        rows = [r for r in rows if r[1] in set(args.officials)]
    if args.limit:
        rows = rows[: args.limit]
    return rows


def tombstone(conn, rows, apply_changes, mode="nav-junk"):
    """Mark non-content rows as deleted. Never hard-deletes."""
    print(f"\n=== {mode}: {len(rows)} rows would be tombstoned "
          f"(deleted_at set, rows retained) ===")
    for _id, oid, url, pub, dsrc, _conf, _title in rows:
        print(f"  {oid:24} {str(pub)[:10] if pub else '-':10} {dsrc or '-':14} {url}")
    if not apply_changes:
        print("\n[dry-run] no changes written")
        return 0
    cur = conn.cursor()
    cur.executemany(
        """
        UPDATE press_releases
        SET deleted_at = now(), updated_at = now()
        WHERE id = %s AND deleted_at IS NULL
        """,
        [(r[0],) for r in rows],
    )
    conn.commit()
    cur.close()
    print(f"\ntombstoned {len(rows)} rows")
    return len(rows)


async def redate(conn, rows, args):
    """Re-fetch each row's detail page and rewrite the date when it improves."""
    log.info("%s: %d candidate rows", args.mode, len(rows))
    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(headers=HEADERS) as client:
        results = await asyncio.gather(
            *(refetch_date(client, r[2], sem, args.delay, r[6]) for r in rows)
        )

    planned, upgraded, unchanged, implausible, errors = [], [], 0, 0, []
    for row, (result, err) in zip(rows, results):
        rec_id, oid, url, pub, dsrc, conf, _title = row
        if result is None:
            errors.append((oid, url, err))
            continue
        new_date = result.value.astimezone(timezone.utc)
        if not is_plausible_date(new_date):
            implausible += 1
            continue
        old_date = pub.astimezone(timezone.utc) if pub else None
        if old_date and old_date.date() == new_date.date():
            # Date already right. Still rewrite provenance when the detail
            # page is better evidence than what the row carries: a row that
            # says listing_page/0.6 but has now been confirmed against the
            # article's own meta tag deserves meta_tag/0.95, otherwise it
            # keeps looking suspect to the clumping checks forever.
            if (conf or 0.0) < result.confidence:
                upgraded.append((rec_id, oid, url, old_date, dsrc, conf, result))
            else:
                unchanged += 1
            continue
        planned.append((rec_id, oid, url, old_date, dsrc, conf, result))

    print(f"\n=== {args.mode}: {len(planned)} rows to re-date, "
          f"{len(upgraded)} to re-provenance "
          f"({unchanged} already correct, {implausible} still implausible, "
          f"{len(errors)} fetch errors) ===")
    print(f"{'official':<22} {'old date':<11} {'old src':<16} "
          f"{'new date':<11} {'new src':<16} url")
    for _id, oid, url, old, dsrc, _c, res in planned:
        print(f"{oid:<22} {str(old.date()) if old else '-':<11} {dsrc or '-':<16} "
              f"{res.value.date()!s:<11} {res.source:<16} {url[:70]}")

    if errors:
        print(f"\n--- {len(errors)} fetch errors (left untouched) ---")
        for oid, url, err in errors[:20]:
            print(f"  {oid:<22} {err:<26} {url[:70]}")
        if len(errors) > 20:
            print(f"  ... {len(errors) - 20} more")

    if not args.apply:
        print("\n[dry-run] no changes written")
        return 0

    # Re-open the connection: a large batch spends minutes fetching pages,
    # and Neon drops the idle session in the meantime ("SSL connection has
    # been closed unexpectedly") so the write would be lost.
    conn = reconnect(conn)
    cur = conn.cursor()
    cur.executemany(
        """
        UPDATE press_releases
        SET published_at = %s,
            date_source = %s,
            date_confidence = %s,
            updated_at = now()
        WHERE id = %s
        """,
        [(r[6].value.astimezone(timezone.utc), r[6].source, r[6].confidence, r[0])
         for r in planned + upgraded],
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"\nupdated {len(planned)} dates, re-provenanced {len(upgraded)} rows")
    return len(planned) + len(upgraded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", required=True,
        choices=["clumped", "out-of-range", "null-date", "dateless-junk",
                 "nav-junk"],
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Write changes. Without it the script only prints its plan.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Explicit no-op default.")
    parser.add_argument(
        "--date-sources", nargs="+", default=["listing_page"],
        help="clumped mode: which date_source values to treat as suspect. "
             "listing_page is the collector bug fixed in backfill.py; the "
             "historical silo_backfill / legacy_backfill / "
             "wp_modified_migration paths clumped the same way.",
    )
    parser.add_argument(
        "--min-clump", type=int, default=10,
        help="clumped mode: rows sharing one day before it counts as a clump",
    )
    parser.add_argument(
        "--window-start", default="2025-01-01",
        help="out-of-range mode: earliest acceptable publication date",
    )
    parser.add_argument("--officials", nargs="*", help="Restrict to these official_ids")
    parser.add_argument("--limit", type=int, help="Cap candidate rows (for testing)")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    if args.dry_run:
        args.apply = False

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    started = time.monotonic()

    rows = select_candidates(conn, args)
    if not rows:
        print(f"{args.mode}: no candidate rows")
        conn.close()
        return

    if args.mode in ("nav-junk", "dateless-junk"):
        changed = tombstone(conn, rows, args.apply, args.mode)
    else:
        changed = asyncio.run(redate(conn, rows, args))

    conn.close()
    print(f"{args.mode}: {changed} rows changed in {time.monotonic() - started:.1f}s")


if __name__ == "__main__":
    sys.exit(main())
