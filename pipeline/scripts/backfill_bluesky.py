"""Backfill all senator Bluesky posts since 2026-01-01.

Reads pipeline/seeds/bluesky_handles.json and walks each verified
senator's author feed via the public Bluesky XRPC. Stops paging the
moment a returned post predates the cutoff. Reposts are skipped — we
archive original authored content only, mirroring our press-release
content scope.

Inserts into social_posts with ON CONFLICT (source, platform_post_id)
DO NOTHING. Re-running is safe and incremental.

Usage:
    python -m pipeline.scripts.backfill_bluesky                 # all senators
    python -m pipeline.scripts.backfill_bluesky --senator markey-edward
    python -m pipeline.scripts.backfill_bluesky --since 2025-01-01
    python -m pipeline.scripts.backfill_bluesky --dry-run

Requires DATABASE_URL to be set (loaded from .env if present).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg2
from psycopg2.extras import Json

ROOT = Path(__file__).resolve().parents[2]
HANDLES = ROOT / "pipeline" / "seeds" / "bluesky_handles.json"
DEFAULT_SINCE = date(2026, 1, 1)
PUBLIC_API = "https://public.api.bsky.app"
PAGE_SIZE = 100
PAGE_DELAY = 0.4  # seconds between pages — be polite to the public API


def load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def summarize_embed(embed: dict | None) -> tuple[str | None, str | None]:
    """Return (kind, summary)."""
    if not embed:
        return None, None
    t = embed.get("$type", "")
    if "external" in t:
        ext = embed.get("external", {})
        return "external", f"link:{ext.get('uri', '')}"
    if "record" in t and "media" in t:
        return "record_with_media", t
    if "record" in t:
        rec = embed.get("record", {})
        return "record", f"quote:{rec.get('uri', '')}"
    if "images" in t:
        imgs = embed.get("images", [])
        return "images", f"images:{len(imgs)}"
    if "video" in t:
        return "video", "video"
    return t or None, None


async def resolve_did(client: httpx.AsyncClient, handle: str) -> str | None:
    try:
        r = await client.get(
            f"{PUBLIC_API}/xrpc/app.bsky.actor.getProfile",
            params={"actor": handle}, timeout=15,
        )
        if r.status_code != 200:
            return None
        return r.json().get("did")
    except Exception:
        return None


async def fetch_page(
    client: httpx.AsyncClient, handle: str, cursor: str | None
) -> dict | None:
    params: dict[str, str | int] = {"actor": handle, "limit": PAGE_SIZE}
    if cursor:
        params["cursor"] = cursor
    for attempt in range(3):
        try:
            r = await client.get(
                f"{PUBLIC_API}/xrpc/app.bsky.feed.getAuthorFeed",
                params=params, timeout=25,
            )
            if r.status_code == 429:
                await asyncio.sleep(2 + attempt * 2)
                continue
            if r.status_code != 200:
                return None
            return r.json()
        except (httpx.ReadTimeout, httpx.ConnectError):
            await asyncio.sleep(1 + attempt)
    return None


def build_row(
    senator_id: str, handle: str, did: str, post: dict, scrape_run: str
) -> dict | None:
    """Convert a feed `post` payload to a social_posts row dict.

    Returns None for posts that should be skipped (no createdAt, missing uri).
    """
    record = post.get("record", {}) or {}
    created = parse_iso(record.get("createdAt", ""))
    at_uri = post.get("uri")
    if not created or not at_uri:
        return None
    reply = record.get("reply") or {}
    parent_uri = (reply.get("parent") or {}).get("uri") if reply else None
    embed_kind, embed_summary = summarize_embed(post.get("embed"))
    return {
        "senator_id": senator_id,
        "source": "bluesky",
        "platform_post_id": at_uri,
        "cid": post.get("cid"),
        "did": did,
        "handle": handle,
        "text": record.get("text", ""),
        "created_at": created,
        "is_reply": parent_uri is not None,
        "reply_parent_uri": parent_uri,
        "is_repost": False,  # we filter reposts upstream
        "embed_kind": embed_kind,
        "embed_summary": embed_summary,
        "lang": (record.get("langs") or [None])[0],
        "raw": post,
        "scrape_run": scrape_run,
    }


def insert_rows(conn, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO social_posts (
            senator_id, source, platform_post_id, cid, did, handle, text,
            created_at, is_reply, reply_parent_uri, is_repost,
            embed_kind, embed_summary, lang, raw, scrape_run
        ) VALUES (
            %(senator_id)s, %(source)s, %(platform_post_id)s, %(cid)s, %(did)s,
            %(handle)s, %(text)s, %(created_at)s, %(is_reply)s,
            %(reply_parent_uri)s, %(is_repost)s, %(embed_kind)s,
            %(embed_summary)s, %(lang)s, %(raw)s, %(scrape_run)s
        )
        ON CONFLICT (source, platform_post_id) DO NOTHING
    """
    cur = conn.cursor()
    inserted = 0
    for row in rows:
        params = {**row, "raw": Json(row["raw"])}
        cur.execute(sql, params)
        inserted += cur.rowcount
    conn.commit()
    cur.close()
    return inserted


async def backfill_handle(
    client: httpx.AsyncClient,
    conn,
    entry: dict,
    since: datetime,
    scrape_run: str,
    dry_run: bool,
) -> dict:
    senator_id = entry["senator_id"]
    handle = entry["handle"]
    did = entry.get("did")
    if not did:
        did = await resolve_did(client, handle)
        if not did:
            return {"senator_id": senator_id, "handle": handle, "error": "did_resolve_failed"}

    cursor: str | None = None
    seen = 0
    inserted_total = 0
    skipped_reposts = 0
    pages = 0
    last_post_at: datetime | None = None
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
                # Reposts — skip.
                skipped_reposts += 1
                continue
            post = entry_item.get("post") or {}
            row = build_row(senator_id, handle, did, post, scrape_run)
            if not row:
                continue
            seen += 1
            if last_post_at is None or row["created_at"] > last_post_at:
                last_post_at = row["created_at"]
            if row["created_at"] < since:
                stop = True
                continue
            rows.append(row)

        if not dry_run and rows:
            inserted_total += insert_rows(conn, rows)

        cursor = page.get("cursor")
        if not cursor:
            break
        await asyncio.sleep(PAGE_DELAY)

    return {
        "senator_id": senator_id,
        "handle": handle,
        "did": did,
        "pages": pages,
        "seen": seen,
        "inserted": inserted_total,
        "skipped_reposts": skipped_reposts,
        "last_post_at": last_post_at.isoformat() if last_post_at else None,
    }


async def amain(args: argparse.Namespace) -> None:
    load_env()
    handles_doc = json.loads(HANDLES.read_text())
    entries = handles_doc["handles"]
    if args.senator:
        entries = [e for e in entries if e["senator_id"] == args.senator]
        if not entries:
            print(f"No entry for senator_id={args.senator}", file=sys.stderr)
            sys.exit(1)

    since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) \
        if args.since else datetime.combine(DEFAULT_SINCE, datetime.min.time(), tzinfo=timezone.utc)

    scrape_run = f"bluesky-backfill-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:6]}"
    print(f"Backfilling {len(entries)} senators since {since.isoformat()}")
    print(f"Scrape run: {scrape_run}")
    if args.dry_run:
        print("DRY RUN — no rows will be written")

    conn = None
    if not args.dry_run:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])

    headers = {"User-Agent": "CapitolReleases-Backfill/1.0"}
    async with httpx.AsyncClient(headers=headers) as client:
        results: list[dict] = []
        for i, entry in enumerate(entries, 1):
            r = await backfill_handle(client, conn, entry, since, scrape_run, args.dry_run)
            results.append(r)
            tag = f"+{r.get('inserted', 0):>4}" if "inserted" in r else "ERR  "
            note = r.get("error") or f"seen={r.get('seen', 0)} pages={r.get('pages', 0)} reposts_skip={r.get('skipped_reposts', 0)}"
            print(f"  [{i:>2}/{len(entries)}] {tag} {r['senator_id']:<28} @{r['handle']:<35} {note}")

    if conn:
        conn.close()

    total_inserted = sum(r.get("inserted") or 0 for r in results)
    total_seen = sum(r.get("seen") or 0 for r in results)
    errors = [r for r in results if r.get("error")]
    print()
    print(f"Done. {total_inserted} rows inserted, {total_seen} posts seen, {len(errors)} errors.")
    if errors:
        for e in errors:
            print(f"  ERROR: {e['senator_id']}/{e['handle']}: {e['error']}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--senator", help="Limit to one senator_id")
    p.add_argument("--since", help="ISO date floor (default 2026-01-01)")
    p.add_argument("--dry-run", action="store_true", help="Walk feeds but write nothing")
    args = p.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
