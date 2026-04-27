"""Audit collection health for senators flagged with null/blocklisted
list_item selectors in senate.json.

Selector hints in the seed are stale-prone signals (recon at point in
time, not runtime status); what matters is whether the daily updater is
actually pulling records. This script compares:

  - DB:   record count since Jan 2025, excluding deleted and photo_release
  - Live: items found on page 1 by extract_listing_items, plus the most
          recent date visible on the listing page
  - Gap:  days since the most recent DB record vs most recent live record

Senators where the DB latest is materially behind the live latest are
the ones to fix first.

Run:
    python -m pipeline.scripts.audit_null_selectors            # all 24
    python -m pipeline.scripts.audit_null_selectors --all-httpx  # widen
    python -m pipeline.scripts.audit_null_selectors --json       # machine output
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg2
from bs4 import BeautifulSoup

from pipeline.lib.http import create_client, fetch_with_retry
from pipeline.backfill import (
    extract_listing_items,
    extract_item_data,
    parse_date,
)

_env = Path(__file__).resolve().parents[1] / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def select_senators(seeds: list[dict], all_httpx: bool) -> list[dict]:
    out = []
    for s in seeds:
        if s.get("collection_method") != "httpx":
            continue
        sel = s.get("selectors") or {}
        list_sel = sel.get("list_item")
        title_sel = sel.get("title")
        is_null_or_bad = (
            not list_sel
            or not title_sel
            or list_sel in ("span.elementor-grid-item", "li.page-item")
        )
        if all_httpx or is_null_or_bad:
            out.append(s)
    return out


def db_stats(conn, senator_id: str) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT count(*)::int,
               max(published_at)::text,
               min(published_at)::text
        FROM press_releases
        WHERE senator_id = %s
          AND deleted_at IS NULL
          AND content_type != 'photo_release'
          AND published_at >= '2025-01-01'
        """,
        (senator_id,),
    )
    row = cur.fetchone()
    cur.close()
    return {
        "db_count": row[0] or 0,
        "db_latest": row[1],
        "db_earliest": row[2],
    }


async def live_probe(client, senator: dict) -> dict:
    url = senator.get("press_release_url", "")
    selectors = senator.get("selectors") or {}
    out = {
        "live_url": url,
        "live_status": None,
        "live_items": 0,
        "live_latest": None,
        "live_oldest": None,
        "live_in_window": 0,
        "error": None,
    }
    if not url:
        out["error"] = "no press_release_url"
        return out
    try:
        resp = await fetch_with_retry(client, url)
        out["live_status"] = resp.status_code
        if resp.status_code != 200:
            return out
        soup = BeautifulSoup(resp.text, "lxml")
        items = extract_listing_items(soup, selectors)
        out["live_items"] = len(items)

        cutoff = date(2025, 1, 1)
        in_window = 0
        latest = None
        oldest = None
        for item in items:
            _, date_text, _ = extract_item_data(item, url, selectors)
            if not date_text:
                continue
            d = parse_date(date_text)
            if not d:
                continue
            d_only = d.date() if hasattr(d, "date") else d
            if d_only >= cutoff:
                in_window += 1
            if latest is None or d_only > latest:
                latest = d_only
            if oldest is None or d_only < oldest:
                oldest = d_only
        out["live_in_window"] = in_window
        out["live_latest"] = latest.isoformat() if latest else None
        out["live_oldest"] = oldest.isoformat() if oldest else None
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def lag_days(db_latest_iso: str | None, live_latest_iso: str | None) -> int | None:
    """Days the DB is behind the live site's most recent listing item."""
    if not db_latest_iso or not live_latest_iso:
        return None
    try:
        db_d = datetime.fromisoformat(db_latest_iso.replace(" ", "T")).date()
    except ValueError:
        return None
    try:
        live_d = date.fromisoformat(live_latest_iso)
    except ValueError:
        return None
    return (live_d - db_d).days


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-httpx", action="store_true", help="Audit every httpx senator, not just null/bad selectors")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of table")
    args = parser.parse_args()

    seed_path = Path(__file__).resolve().parents[1] / "seeds" / "senate.json"
    seeds = json.loads(seed_path.read_text())["members"]
    senators = select_senators(seeds, args.all_httpx)

    db_url = os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(db_url)

    rows = []
    async with create_client() as client:
        for s in senators:
            sid = s["senator_id"]
            db = db_stats(conn, sid)
            live = await live_probe(client, s)
            row = {
                "senator_id": sid,
                "parser_family": s.get("parser_family"),
                "list_item": (s.get("selectors") or {}).get("list_item"),
                "confidence": s.get("confidence"),
                **db,
                **live,
                "lag_days": lag_days(db["db_latest"], live["live_latest"]),
            }
            rows.append(row)

    conn.close()

    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return

    # Table output, sorted by lag_days descending (worst first), nulls last.
    rows.sort(key=lambda r: (-1 if r["lag_days"] is None else r["lag_days"]), reverse=True)

    print(f"\nAudited {len(rows)} senators\n")
    print(f"{'senator_id':25s} {'cfg':5s} {'db':>5s} {'live':>5s} {'inwin':>5s} {'lag':>5s}  {'db_latest':12s} {'live_latest':12s}  flags")
    print("-" * 120)
    for r in rows:
        flags = []
        if r["live_status"] != 200:
            flags.append(f"HTTP{r['live_status']}")
        if r["error"]:
            flags.append("ERR")
        if r["live_items"] == 0 and r["live_status"] == 200:
            flags.append("0-items")
        if r["lag_days"] is not None and r["lag_days"] > 14:
            flags.append(f"lag>{r['lag_days']}d")
        if r["db_count"] == 0:
            flags.append("db=0")
        if r["live_in_window"] > 0 and r["db_count"] > 0:
            ratio = r["db_count"] / max(r["live_in_window"], 1)
            if ratio < 0.5:
                flags.append("undercollect?")
        cfg = "null" if not r["list_item"] else "bad" if r["list_item"] in ("span.elementor-grid-item", "li.page-item") else "ok"
        print(
            f"{r['senator_id']:25s} {cfg:5s} {r['db_count']:>5d} {r['live_items']:>5d} {r['live_in_window']:>5d} "
            f"{(str(r['lag_days']) + 'd' if r['lag_days'] is not None else '-'):>5s}  "
            f"{(r['db_latest'] or '-')[:10]:12s} {(r['live_latest'] or '-')[:10]:12s}  {' '.join(flags)}"
        )


if __name__ == "__main__":
    asyncio.run(main())
