"""Full 100-senator Bluesky recon.

Two-stage discovery for every current US senator:

1. Scrape the senator's senate.gov pages (homepage + press page + /contact)
   for any bsky.app link in the HTML. Most senators link socials in their
   site footer. A direct link from a .senate.gov domain is the strongest
   verification signal we can cheaply collect.

2. For senators with no bsky.app link found, search Bluesky's public actor
   index by name. Hits are flagged "search" provenance — must be reviewed
   before promoting to seeds/bluesky_handles.json. Never auto-trusted.

For every resolved handle we then pull profile metadata (DID, follower
count, total post count) and the last 100 posts to compute activity:
last post timestamp, posts in last 30 days, posts in last 7 days.

Outputs:
  - pipeline/recon/bluesky_recon_results.json (machine-readable, all data)
  - pipeline/recon/bluesky_recon_report.md (sorted activity table)

Run:
  .venv/bin/python -m pipeline.recon.bluesky_recon
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "pipeline" / "seeds" / "senate.json"
OUT_JSON = ROOT / "pipeline" / "recon" / "bluesky_recon_results.json"
OUT_MD = ROOT / "pipeline" / "recon" / "bluesky_recon_report.md"

PUBLIC_API = "https://public.api.bsky.app"
BSKY_LINK = re.compile(r"https?://(?:www\.)?bsky\.app/profile/([^/\"'?#\s>]+)", re.I)

UA = "CapitolReleases-Recon/1.0 (https://github.com/tbrown034)"

SCRAPE_CONCURRENCY = 10
API_CONCURRENCY = 5


async def fetch_html(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        r = await client.get(url, timeout=15, follow_redirects=True)
        if r.status_code >= 400:
            return None
        return r.text
    except Exception:
        return None


def extract_bsky_handles(html: str) -> list[str]:
    """Return all bsky handles linked from the HTML, deduplicated, ordered."""
    if not html:
        return []
    seen: list[str] = []
    for m in BSKY_LINK.finditer(html):
        h = m.group(1).strip().lower()
        # Reject obvious non-handles (search/post URLs)
        if h in ("search", "settings", "feeds", "lists"):
            continue
        if h.startswith("did:"):
            # DID-based profile URL — keep the DID
            pass
        if h not in seen:
            seen.append(h)
    return seen


def candidate_pages(senator: dict) -> list[str]:
    """Pages most likely to expose a Bluesky link."""
    base = senator.get("official_url", "").rstrip("/")
    pages = [base, senator.get("press_release_url", "")]
    if base:
        pages += [
            f"{base}/contact",
            f"{base}/contact/",
            f"{base}/about",
        ]
    return [p for p in pages if p]


async def scrape_senator(
    client: httpx.AsyncClient, senator: dict, sem: asyncio.Semaphore
) -> dict:
    """Look for bsky links on a senator's senate.gov pages."""
    sid = senator["senator_id"]
    found: list[tuple[str, str]] = []  # (handle, source_url)
    pages_checked: list[str] = []
    async with sem:
        for url in candidate_pages(senator):
            html = await fetch_html(client, url)
            pages_checked.append(url)
            if not html:
                continue
            for handle in extract_bsky_handles(html):
                if not any(h == handle for h, _ in found):
                    found.append((handle, url))
            if found:
                break  # first match is enough; footer is consistent
    return {
        "senator_id": sid,
        "full_name": senator["full_name"],
        "state": senator["state"],
        "party": senator["party"],
        "site_handles": [{"handle": h, "verified_via": u} for h, u in found],
        "pages_checked": pages_checked,
    }


async def search_bluesky_actor(
    client: httpx.AsyncClient, query: str
) -> list[dict]:
    """Bluesky public typeahead. Returns actor candidates."""
    try:
        r = await client.get(
            f"{PUBLIC_API}/xrpc/app.bsky.actor.searchActorsTypeahead",
            params={"q": query, "limit": 10},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("actors", [])
    except Exception:
        return []


async def get_profile(client: httpx.AsyncClient, actor: str) -> dict | None:
    try:
        r = await client.get(
            f"{PUBLIC_API}/xrpc/app.bsky.actor.getProfile",
            params={"actor": actor},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


async def get_recent_posts(
    client: httpx.AsyncClient, actor: str, limit: int = 100
) -> list[dict]:
    try:
        r = await client.get(
            f"{PUBLIC_API}/xrpc/app.bsky.feed.getAuthorFeed",
            params={"actor": actor, "limit": limit},
            timeout=20,
        )
        if r.status_code != 200:
            return []
        return r.json().get("feed", [])
    except Exception:
        return []


def parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def activity_stats(feed: list[dict]) -> dict:
    """Compute last-post + 7d / 30d post counts from up to 100 posts."""
    now = datetime.now(timezone.utc)
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)
    last: datetime | None = None
    n7 = n30 = 0
    own = 0  # posts authored by the actor (vs reposts)
    for entry in feed:
        post = entry.get("post", {})
        record = post.get("record", {})
        created = parse_iso(record.get("createdAt", ""))
        if not created:
            continue
        # Skip reposts (reason present in entry); we want author posts
        if entry.get("reason"):
            continue
        own += 1
        if last is None or created > last:
            last = created
        if created >= d7:
            n7 += 1
        if created >= d30:
            n30 += 1
    return {
        "post_sample_size": own,
        "last_post_at": last.isoformat() if last else None,
        "posts_last_7d": n7,
        "posts_last_30d": n30,
    }


async def enrich_handle(
    client: httpx.AsyncClient, handle: str, sem: asyncio.Semaphore
) -> dict:
    async with sem:
        prof = await get_profile(client, handle)
        if not prof:
            return {"handle": handle, "resolved": False}
        feed = await get_recent_posts(client, handle)
    stats = activity_stats(feed)
    return {
        "handle": prof.get("handle"),
        "did": prof.get("did"),
        "display_name": prof.get("displayName"),
        "description": (prof.get("description") or "")[:280],
        "followers": prof.get("followersCount"),
        "follows": prof.get("followsCount"),
        "posts_total": prof.get("postsCount"),
        "resolved": True,
        **stats,
    }


def name_query(senator: dict) -> str:
    """Drop courtesy/middle for typeahead. e.g. 'Angela D. Alsobrooks' → 'Angela Alsobrooks'."""
    parts = [p for p in senator["full_name"].split() if not p.endswith(".")]
    if len(parts) >= 2:
        return f"{parts[0]} {parts[-1]}"
    return senator["full_name"]


async def search_fallback(
    client: httpx.AsyncClient, senator: dict, sem: asyncio.Semaphore
) -> list[dict]:
    """Probe Bluesky search for senator names that had no .senate.gov link."""
    async with sem:
        cands = await search_bluesky_actor(client, name_query(senator))
    out = []
    for c in cands[:5]:
        out.append({
            "handle": c.get("handle"),
            "display_name": c.get("displayName"),
            "description": (c.get("description") or "")[:200],
            "followers": c.get("followersCount"),
        })
    return out


async def main() -> None:
    seed = json.loads(SEED.read_text())
    members = seed["members"]
    print(f"Loaded {len(members)} senators")

    headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}
    timeout = httpx.Timeout(20.0, connect=10.0)
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)

    async with httpx.AsyncClient(
        headers=headers, timeout=timeout, limits=limits
    ) as client:
        # Stage 1: scrape senate.gov pages
        sem = asyncio.Semaphore(SCRAPE_CONCURRENCY)
        scrape_tasks = [scrape_senator(client, s, sem) for s in members]
        scraped: list[dict] = []
        for i, coro in enumerate(asyncio.as_completed(scrape_tasks), 1):
            r = await coro
            scraped.append(r)
            tag = "BSKY" if r["site_handles"] else "----"
            print(f"  [{i:>3}/100] {tag} {r['senator_id']:<28} {r['state']} ({r['party']})")

        # Stage 2: enrich every handle that came from senate.gov directly
        api_sem = asyncio.Semaphore(API_CONCURRENCY)
        all_handles: dict[str, dict] = {}
        for s in scraped:
            for sh in s["site_handles"]:
                all_handles.setdefault(sh["handle"], {"handle": sh["handle"]})

        print(f"\nEnriching {len(all_handles)} handles via Bluesky public API...")
        enrich_tasks = [
            enrich_handle(client, h, api_sem) for h in all_handles
        ]
        enriched_list = await asyncio.gather(*enrich_tasks)
        enriched_by_handle = {e.get("handle"): e for e in enriched_list if e.get("handle")}
        # Also keyed by lookup handle (resolved handle may differ in case)
        for original, e in zip(all_handles.keys(), enriched_list):
            enriched_by_handle.setdefault(original.lower(), e)

        # Stage 3: search fallback for senators without a verified link
        missing = [s for s in scraped if not s["site_handles"]]
        print(f"\nSearch-fallback for {len(missing)} senators with no senate.gov link...")
        fb_tasks = [search_fallback(client, members_by_id[s["senator_id"]], api_sem)
                    for s in missing for members_by_id in [{m["senator_id"]: m for m in members}]]
        # Simpler: do it sequentially-async without dict-comp gymnastics
        members_by_id = {m["senator_id"]: m for m in members}
        fb_tasks = [search_fallback(client, members_by_id[s["senator_id"]], api_sem)
                    for s in missing]
        fb_results = await asyncio.gather(*fb_tasks)
        for s, fb in zip(missing, fb_results):
            s["search_candidates"] = fb

    # Merge enrichment into scraped records
    for s in scraped:
        s["site_handles_enriched"] = []
        for sh in s["site_handles"]:
            e = enriched_by_handle.get(sh["handle"].lower()) or {"handle": sh["handle"], "resolved": False}
            s["site_handles_enriched"].append({**sh, **e})

    # Sort scraped by senator_id for stable output
    scraped.sort(key=lambda r: r["senator_id"])

    OUT_JSON.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_senators": len(members),
        "with_site_link": sum(1 for s in scraped if s["site_handles"]),
        "results": scraped,
    }, indent=2))
    print(f"\nWrote {OUT_JSON.relative_to(ROOT)}")

    write_report(scraped)
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")


def write_report(scraped: list[dict]) -> None:
    """Markdown report with two tables: verified senators + search-only candidates."""
    verified = [s for s in scraped if s["site_handles_enriched"]]
    missing = [s for s in scraped if not s["site_handles_enriched"]]

    # Sort verified by activity (posts in last 30d desc), then followers desc
    def sort_key(s):
        h = s["site_handles_enriched"][0]
        return (
            -(h.get("posts_last_30d") or 0),
            -(h.get("followers") or 0),
        )

    verified.sort(key=sort_key)

    lines: list[str] = []
    lines.append("# Bluesky recon — 100 US senators")
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append("")
    lines.append(f"- **{len(verified)}** of 100 senators link a Bluesky profile from their senate.gov site")
    lines.append(f"- **{len(missing)}** have no Bluesky link on their official site")
    party_counts: dict[str, int] = {}
    for s in verified:
        party_counts[s["party"]] = party_counts.get(s["party"], 0) + 1
    lines.append(f"- Party split among verified: " + ", ".join(f"{k}={v}" for k, v in sorted(party_counts.items())))
    lines.append("")
    lines.append("## Verified — sorted by 30-day activity")
    lines.append("")
    lines.append("| Senator | State | Party | Handle | Followers | Total posts | Last 30d | Last 7d | Last post |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---|")
    for s in verified:
        h = s["site_handles_enriched"][0]
        last = h.get("last_post_at") or ""
        if last:
            last = last[:10]
        followers = h.get("followers")
        total = h.get("posts_total")
        n30 = h.get("posts_last_30d")
        n7 = h.get("posts_last_7d")
        handle = h.get("handle", "—")
        link = f"[{handle}](https://bsky.app/profile/{handle})" if handle and handle != "—" else "—"
        lines.append(
            f"| {s['full_name']} | {s['state']} | {s['party']} | {link} "
            f"| {followers if followers is not None else '—'} "
            f"| {total if total is not None else '—'} "
            f"| {n30 if n30 is not None else '—'} "
            f"| {n7 if n7 is not None else '—'} "
            f"| {last or '—'} |"
        )
    lines.append("")
    lines.append("## Senators with no Bluesky link on senate.gov")
    lines.append("")
    lines.append("Search-only candidates need manual verification before they can be promoted to `seeds/bluesky_handles.json`.")
    lines.append("")
    lines.append("| Senator | State | Party | Top search candidate | Followers |")
    lines.append("|---|---|---|---|---:|")
    for s in sorted(missing, key=lambda r: (r["state"], r["full_name"])):
        cands = s.get("search_candidates") or []
        top = cands[0] if cands else None
        if top:
            handle = top.get("handle", "—")
            link = f"[{handle}](https://bsky.app/profile/{handle}) — {top.get('display_name') or ''}"
            followers = top.get("followers") if top.get("followers") is not None else "—"
        else:
            link = "—"
            followers = "—"
        lines.append(f"| {s['full_name']} | {s['state']} | {s['party']} | {link} | {followers} |")
    lines.append("")
    OUT_MD.write_text("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
