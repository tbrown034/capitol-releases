"""Bluesky collector skeleton.

Capitol Releases extends to Bluesky as a content stream parallel to press
releases. The architectural model:

  - Each senator has at most one verified Bluesky handle, listed in
    pipeline/seeds/bluesky_handles.json with verification provenance.
  - Backfill uses the public XRPC endpoint app.bsky.feed.getAuthorFeed
    (no auth required for public posts).
  - Real-time ingest connects to the AT Protocol Jetstream WebSocket and
    filters events by the set of known senator DIDs.
  - Deletes are first-class — Jetstream broadcasts every deletion as a
    separate event. We tombstone the post (deleted_at set) but keep the
    original text. This is the same archival permanence press releases get.

This module ships the skeleton. Real ingestion (writes to DB) lands once
the handle directory is populated and the schema migration is in place.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator

import httpx

PUBLIC_API_BASE = "https://public.api.bsky.app"
JETSTREAM_WSS = (
    "wss://jetstream2.us-east.bsky.network/subscribe"
    "?wantedCollections=app.bsky.feed.post"
)


@dataclass(frozen=True)
class BlueskyPost:
    """Normalized post record. Mirrors the fields the press_releases table
    will gain via the next migration."""

    senator_id: str
    handle: str
    did: str
    at_uri: str
    cid: str
    text: str
    created_at: datetime
    reply_parent_uri: str | None
    embed_summary: str | None  # JSON-stringified link/quote summary
    raw: dict


async def resolve_handle(handle: str, *, client: httpx.AsyncClient) -> dict:
    """Resolve a handle to its DID + profile metadata.

    Used to (a) confirm the handle is live before adding it to the seed,
    and (b) populate the `did` field which is the stable identifier for
    Jetstream filtering (handles can change; DIDs cannot).
    """
    r = await client.get(
        f"{PUBLIC_API_BASE}/xrpc/app.bsky.actor.getProfile",
        params={"actor": handle},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


async def fetch_author_feed(
    handle: str,
    *,
    client: httpx.AsyncClient,
    limit: int = 100,
    cursor: str | None = None,
) -> dict:
    """One page of an author's feed. Caller paginates via cursor.

    Bluesky's public XRPC is permissive (no auth, generous rate limits)
    and returns posts in reverse chronological order with a cursor token.
    """
    params: dict[str, str | int] = {"actor": handle, "limit": limit}
    if cursor:
        params["cursor"] = cursor
    r = await client.get(
        f"{PUBLIC_API_BASE}/xrpc/app.bsky.feed.getAuthorFeed",
        params=params,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


async def backfill_since(
    senator_id: str,
    handle: str,
    did: str,
    since: datetime,
    *,
    client: httpx.AsyncClient,
) -> AsyncIterator[BlueskyPost]:
    """Walk an author's feed backwards until `since`, yielding normalized
    posts. Stops the moment a page returns an item older than `since`."""
    cursor: str | None = None
    while True:
        page = await fetch_author_feed(handle, client=client, cursor=cursor)
        feed = page.get("feed", [])
        if not feed:
            return
        for entry in feed:
            post = entry.get("post", {})
            record = post.get("record", {})
            created_raw = record.get("createdAt")
            if not created_raw:
                continue
            created = _parse_iso(created_raw)
            if created < since:
                return
            yield _normalize(senator_id, handle, did, post)
        cursor = page.get("cursor")
        if not cursor:
            return
        # Be polite to the public API.
        await asyncio.sleep(0.5)


def _normalize(
    senator_id: str, handle: str, did: str, post: dict
) -> BlueskyPost:
    record = post.get("record", {})
    reply = record.get("reply", {}) or {}
    parent = (reply.get("parent") or {}).get("uri")
    embed = post.get("embed")
    return BlueskyPost(
        senator_id=senator_id,
        handle=handle,
        did=did,
        at_uri=post["uri"],
        cid=post["cid"],
        text=record.get("text", ""),
        created_at=_parse_iso(record["createdAt"]),
        reply_parent_uri=parent,
        embed_summary=_summarize_embed(embed) if embed else None,
        raw=post,
    )


def _summarize_embed(embed: dict) -> str:
    """Compact human-readable embed summary (link card / quote / images)."""
    t = embed.get("$type", "")
    if "external" in t:
        ext = embed.get("external", {})
        return f"link:{ext.get('uri', '')}"
    if "record" in t:
        rec = embed.get("record", {})
        return f"quote:{rec.get('uri', '')}"
    if "images" in t:
        imgs = embed.get("images", [])
        return f"images:{len(imgs)}"
    return t or "unknown"


def _parse_iso(iso: str) -> datetime:
    # Bluesky ISO timestamps include sub-second precision and Z suffix.
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))
