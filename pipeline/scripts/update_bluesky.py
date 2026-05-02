"""Incremental daily Bluesky updater.

Walks each verified senator's author feed forward from the most recent
post we already have in `social_posts`. Stops as soon as a returned
post's created_at is <= our local max for that senator. Designed to run
on the daily cron alongside the press-release update.

For senators with zero rows, falls back to the same 2026-01-01 cutoff
the backfill uses, so a newly added handle gets a full first-run pull
without manual intervention.

Usage:
    python -m pipeline.scripts.update_bluesky                # all handles
    python -m pipeline.scripts.update_bluesky --senator markey-edward
    python -m pipeline.scripts.update_bluesky --dry-run

Re-runs are safe (ON CONFLICT DO NOTHING).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg2

ROOT = Path(__file__).resolve().parents[2]
HANDLES = ROOT / "pipeline" / "seeds" / "bluesky_handles.json"

# Reuse the backfill primitives — they already handle paging, rate limits,
# and row construction. We only override the stop condition.
from pipeline.scripts.backfill_bluesky import (  # noqa: E402
    DEFAULT_SINCE,
    PAGE_DELAY,
    build_row,
    fetch_page,
    insert_rows,
    load_env,
    parse_iso,
    resolve_did,
)


async def update_one(
    client: httpx.AsyncClient,
    conn,
    entry: dict,
    floor: datetime,
    scrape_run: str,
    dry_run: bool,
) -> dict:
    """Walk an author's feed forward until we hit `floor` (last-known created_at
    for this senator, or the global cutoff for first-runs)."""
    official_id = entry["official_id"]
    handle = entry["handle"]
    did = entry.get("did") or await resolve_did(client, handle)
    if not did:
        return {"official_id": official_id, "handle": handle, "error": "did_resolve_failed"}

    cursor: str | None = None
    seen = 0
    inserted_total = 0
    skipped_reposts = 0
    pages = 0
    stop = False

    while not stop:
        page = await fetch_page(client, handle, cursor)
        pages += 1
        if not page:
            break
        feed = page.get("feed", []) or []
        if not feed:
            break

        rows: list[dict] = []
        for entry_item in feed:
            if entry_item.get("reason"):
                skipped_reposts += 1
                continue
            post = entry_item.get("post") or {}
            row = build_row(official_id, handle, did, post, scrape_run)
            if not row:
                continue
            seen += 1
            if row["created_at"] <= floor:
                # We've reached previously-captured territory — stop after
                # finishing this page's still-unseen rows.
                stop = True
                continue
            rows.append(row)

        if not dry_run and rows:
            inserted_total += insert_rows(conn, rows)

        if stop:
            break
        cursor = page.get("cursor")
        if not cursor:
            break
        await asyncio.sleep(PAGE_DELAY)

    return {
        "official_id": official_id,
        "handle": handle,
        "pages": pages,
        "seen": seen,
        "inserted": inserted_total,
        "skipped_reposts": skipped_reposts,
        "floor": floor.isoformat(),
    }


def per_senator_floor(conn) -> dict[str, datetime]:
    """Map official_id -> max(created_at) of their existing posts."""
    cur = conn.cursor()
    cur.execute(
        "SELECT official_id, max(created_at) FROM social_posts GROUP BY official_id"
    )
    out: dict[str, datetime] = {}
    for sid, ts in cur.fetchall():
        if ts is not None:
            out[sid] = ts
    cur.close()
    return out


async def amain(args: argparse.Namespace) -> None:
    load_env()
    handles_doc = json.loads(HANDLES.read_text())
    entries = handles_doc["handles"]
    if args.senator:
        entries = [e for e in entries if e["official_id"] == args.senator]
        if not entries:
            print(f"No entry for official_id={args.senator}", file=sys.stderr)
            sys.exit(1)

    if args.dry_run:
        print("DRY RUN — no rows will be written")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    floors = per_senator_floor(conn)
    cutoff = datetime.combine(DEFAULT_SINCE, datetime.min.time(), tzinfo=timezone.utc)

    scrape_run = f"bluesky-update-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:6]}"
    print(f"Updating {len(entries)} handles. scrape_run={scrape_run}")

    headers = {"User-Agent": "CapitolReleases-Update/1.0"}
    async with httpx.AsyncClient(headers=headers) as client:
        results: list[dict] = []
        for i, entry in enumerate(entries, 1):
            floor = floors.get(entry["official_id"], cutoff)
            r = await update_one(client, conn, entry, floor, scrape_run, args.dry_run)
            results.append(r)
            tag = f"+{r.get('inserted', 0):>3}" if "inserted" in r else "ERR "
            note = r.get("error") or f"seen={r.get('seen', 0)} pages={r.get('pages', 0)}"
            print(f"  [{i:>2}/{len(entries)}] {tag} {r['official_id']:<28} @{r['handle']:<35} {note}")

    conn.close()
    total_inserted = sum(r.get("inserted") or 0 for r in results)
    errors = [r for r in results if r.get("error")]
    print(f"\nUpdate complete. {total_inserted} new posts. {len(errors)} errors.")
    for e in errors:
        print(f"  ERROR: {e['official_id']}/{e['handle']}: {e['error']}")
    # Non-zero exit on errors lets CI flag without aborting the whole pipeline
    if errors and not args.dry_run:
        sys.exit(2)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--senator", help="Limit to one official_id")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
