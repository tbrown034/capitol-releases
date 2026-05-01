"""Cross-reference public Bluesky starter packs against senate.json.

Augments bluesky_recon.py: that script discovered 35 senators by direct
.gov-footer link. This script pulls the AT Protocol starter packs known
to curate US senators, walks every list-item, and matches each member
to a row in senate.json. Output flags:

  - Already-verified senators (overlap sanity check)
  - New candidate handles for senators we missed
  - Starter-pack entries that don't match any current senator (drift /
    former members / committees / parodies)

Each candidate carries the set of starter packs it appears in. A
handle that lives in 4 different curated packs created by different
authors is much stronger evidence than one that lives in one.

Run:
  .venv/bin/python -m pipeline.recon.bluesky_starterpack_xref
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "pipeline" / "seeds" / "senate.json"
PRIOR = ROOT / "pipeline" / "recon" / "bluesky_recon_results.json"
OUT_JSON = ROOT / "pipeline" / "recon" / "bluesky_starterpack_xref.json"
OUT_MD = ROOT / "pipeline" / "recon" / "bluesky_starterpack_xref.md"

PUBLIC_API = "https://public.api.bsky.app"

# Curated starter packs known from search results. Each is (uri, label).
# Authorship matters for trust weighting — Whitehouse's pack is .senate.gov-authored.
PACKS = [
    ("at://whitehouse.senate.gov/app.bsky.graph.starterpack/3lbayvlfpmb2o",
     "Senate Democrats (by whitehouse.senate.gov)"),
    ("at://maxberger.bsky.social/app.bsky.graph.starterpack/3laptkr7stu2c",
     "Members of Congress"),
    ("at://ganeshsriram.bsky.social/app.bsky.graph.starterpack/3lbit6h3rqa2r",
     "US Senate, Senators, and Related Stuff"),
    ("at://amychomd.bsky.social/app.bsky.graph.starterpack/3lbakklobiy2g",
     "US Senators (amychomd)"),
    ("at://amymh.bsky.social/app.bsky.graph.starterpack/3lg3sfzdxoe27",
     "US Senators and Committees (amymh)"),
    ("at://liberalresistance.bsky.social/app.bsky.graph.starterpack/3ljy3af7llt2r",
     "2025 US Senators on Bluesky"),
    ("at://bernhardkappe.bsky.social/app.bsky.graph.starterpack/3li36vx3oxw2v",
     "US Senators on BlueSky"),
    ("at://ariellaelm.bsky.social/app.bsky.graph.starterpack/3lh2kmo4mnz2b",
     "Dem Senators and committees"),
]


async def get_pack_list_uri(client: httpx.AsyncClient, pack_uri: str) -> str | None:
    r = await client.get(
        f"{PUBLIC_API}/xrpc/app.bsky.graph.getStarterPack",
        params={"starterPack": pack_uri}, timeout=20,
    )
    if r.status_code != 200:
        return None
    return r.json().get("starterPack", {}).get("list", {}).get("uri")


async def get_list_members(client: httpx.AsyncClient, list_uri: str) -> list[dict]:
    """Walk every page of a list. Returns raw subject dicts."""
    members: list[dict] = []
    cursor: str | None = None
    while True:
        params = {"list": list_uri, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        r = await client.get(
            f"{PUBLIC_API}/xrpc/app.bsky.graph.getList",
            params=params, timeout=20,
        )
        if r.status_code != 200:
            return members
        d = r.json()
        for it in d.get("items", []):
            members.append(it.get("subject", {}))
        cursor = d.get("cursor")
        if not cursor:
            return members


def normalize_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def lastname_token(senator: dict) -> str:
    """Best lastname token to match against a handle."""
    # senator_id is like "alsobrooks-angela" → "alsobrooks"
    sid = senator["senator_id"]
    return sid.split("-")[0]


def firstname_token(senator: dict) -> str:
    sid = senator["senator_id"]
    parts = sid.split("-")
    return parts[1] if len(parts) > 1 else ""


def match_member(subject: dict, members_by_id: dict) -> tuple[str, float, str] | None:
    """Match a Bluesky subject to a senator. Returns (senator_id, score, reason).

    Heuristics, in descending strength:
      1. handle ends with `<lastname>.senate.gov` → 1.0
      2. handle host == `<lastname>.senate.gov` → 1.0
      3. handle contains both first and last name tokens → 0.85
      4. display_name contains "Senator <Last>" or "Sen. <Last>" → 0.8
      5. display_name normalized contains both first and last → 0.75
      6. handle contains lastname AND description has "U.S. Senator" → 0.7
    """
    handle = (subject.get("handle") or "").lower()
    display = subject.get("displayName") or ""
    description = subject.get("description") or ""
    norm_display = normalize_text(display)
    norm_descr = normalize_text(description)

    # Exact .senate.gov-handle match wins outright
    for sid, sen in members_by_id.items():
        last = lastname_token(sen)
        if not last:
            continue
        if handle == f"{last}.senate.gov":
            return sid, 1.0, f"handle == {last}.senate.gov"

    # Other heuristics
    best: tuple[str, float, str] | None = None
    for sid, sen in members_by_id.items():
        last = lastname_token(sen)
        first = firstname_token(sen)
        if not last:
            continue
        score = 0.0
        reasons = []

        if last in handle and first and first in handle:
            score = max(score, 0.85)
            reasons.append(f"handle contains {first}+{last}")

        if first and last:
            if first in norm_display and last in norm_display:
                score = max(score, 0.75)
                reasons.append("display name has first+last")

        # "Senator <Last>" / "Sen. <Last>" patterns
        if re.search(rf"\b(senator|sen\.?)\s+[a-z\.\s]*\b{re.escape(last)}\b",
                     display.lower()):
            score = max(score, 0.8)
            reasons.append("display 'Senator <last>'")

        if last in handle and "ussenator" in norm_descr:
            score = max(score, 0.7)
            reasons.append("handle has lastname + description 'US Senator'")

        # Penalize obvious parody/anti markers
        if any(kw in description.lower() for kw in [
            "parody", "fake", "not the asshole", "is a", "neighbor of",
            "is dead", "is toast", "hates america", "concerned today",
            "called the fbi", "mirror", "sucks nuts",
        ]):
            score *= 0.3
            reasons.append("parody/anti penalty")

        if score > 0 and (best is None or score > best[1]):
            best = (sid, score, "; ".join(reasons))
    return best


async def main() -> None:
    seed = json.loads(SEED.read_text())
    members = seed["members"]
    members_by_id = {m["senator_id"]: m for m in members}

    prior = json.loads(PRIOR.read_text()) if PRIOR.exists() else {"results": []}
    prior_verified: dict[str, str] = {}
    for r in prior.get("results", []):
        if r.get("site_handles_enriched"):
            prior_verified[r["senator_id"]] = r["site_handles_enriched"][0].get("handle", "")

    # Build map: senator_id -> {handle: {pack labels}}
    candidates: dict[str, dict[str, dict]] = {}
    unmatched: list[dict] = []  # subjects that didn't map to any senator
    pack_counts: dict[str, int] = {}

    async with httpx.AsyncClient(headers={"User-Agent": "CapitolReleases-Recon/1.0"}) as client:
        for pack_uri, label in PACKS:
            list_uri = await get_pack_list_uri(client, pack_uri)
            if not list_uri:
                print(f"  SKIP unable to resolve {label}")
                continue
            subjects = await get_list_members(client, list_uri)
            pack_counts[label] = len(subjects)
            print(f"  {label}: {len(subjects)} members")
            for subj in subjects:
                handle = (subj.get("handle") or "").lower()
                if not handle or handle == "handle.invalid":
                    continue
                m = match_member(subj, members_by_id)
                if not m:
                    unmatched.append({"handle": handle, "displayName": subj.get("displayName"), "pack": label})
                    continue
                sid, score, reason = m
                bucket = candidates.setdefault(sid, {})
                rec = bucket.setdefault(handle, {
                    "handle": handle,
                    "did": subj.get("did"),
                    "displayName": subj.get("displayName"),
                    "description": (subj.get("description") or "")[:280],
                    "match_score": 0.0,
                    "match_reasons": set(),
                    "packs": set(),
                })
                rec["match_score"] = max(rec["match_score"], score)
                rec["match_reasons"].add(reason)
                rec["packs"].add(label)

    # Stringify sets for JSON output
    out_candidates = {}
    for sid, by_handle in candidates.items():
        out_candidates[sid] = []
        for h, rec in by_handle.items():
            out_candidates[sid].append({
                **rec,
                "match_reasons": sorted(rec["match_reasons"]),
                "packs": sorted(rec["packs"]),
                "pack_count": len(rec["packs"]),
            })
        out_candidates[sid].sort(key=lambda r: (-r["pack_count"], -r["match_score"]))

    OUT_JSON.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "packs_consulted": [{"uri": u, "label": l, "members": pack_counts.get(l, 0)} for u, l in PACKS],
        "candidates_by_senator": out_candidates,
        "unmatched_subjects": unmatched[:200],
    }, indent=2))
    print(f"\nWrote {OUT_JSON.relative_to(ROOT)}")

    # Markdown report
    lines: list[str] = []
    lines.append("# Bluesky starter-pack cross-reference")
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append("")
    lines.append("Cross-references **8 curated public Bluesky starter packs** against `senate.json`.")
    lines.append("Each candidate is scored by handle/display-name match strength and the number of independent packs it appears in.")
    lines.append("")
    lines.append("## Packs consulted")
    lines.append("")
    for u, l in PACKS:
        lines.append(f"- {l} — {pack_counts.get(l, 0)} members")
    lines.append("")

    # Section 1: senators NOT in our prior verified set who now have a candidate
    new_hits = sorted(
        [sid for sid in candidates if sid not in prior_verified],
        key=lambda s: members_by_id[s]["full_name"],
    )

    lines.append(f"## New candidates — {len(new_hits)} senators we missed in the .gov-footer pass")
    lines.append("")
    lines.append("| Senator | State | Party | Best handle | Score | Packs | Display name |")
    lines.append("|---|---|---|---|---:|---:|---|")
    for sid in new_hits:
        sen = members_by_id[sid]
        best = out_candidates[sid][0]
        link = f"[{best['handle']}](https://bsky.app/profile/{best['handle']})"
        lines.append(
            f"| {sen['full_name']} | {sen['state']} | {sen['party']} | {link} "
            f"| {best['match_score']:.2f} | {best['pack_count']} "
            f"| {best.get('displayName') or ''} |"
        )
    lines.append("")

    # Section 2: senators with candidates but no prior verification AND multiple packs - high confidence
    high_conf = [sid for sid in new_hits if out_candidates[sid][0]["pack_count"] >= 2 and out_candidates[sid][0]["match_score"] >= 0.75]
    lines.append(f"### High confidence subset ({len(high_conf)} senators with score ≥0.75 and present in 2+ packs)")
    lines.append("")
    for sid in high_conf:
        sen = members_by_id[sid]
        best = out_candidates[sid][0]
        lines.append(f"- **{sen['full_name']}** ({sen['state']}-{sen['party']}) → `{best['handle']}` (score {best['match_score']:.2f}, {best['pack_count']} packs)")
    lines.append("")

    # Section 3: still missing
    still_missing = sorted(
        [sid for sid in members_by_id if sid not in prior_verified and sid not in candidates],
        key=lambda s: (members_by_id[s]["state"], members_by_id[s]["full_name"]),
    )
    lines.append(f"## Still no Bluesky candidate — {len(still_missing)} senators")
    lines.append("")
    lines.append("Not linked from senate.gov AND not in any of the 8 starter packs. Treat as: probably no Bluesky presence, or presence so obscure no curator has cataloged it.")
    lines.append("")
    for sid in still_missing:
        sen = members_by_id[sid]
        lines.append(f"- {sen['full_name']} ({sen['state']}-{sen['party']})")
    lines.append("")

    # Section 4: senators verified by .gov AND confirmed by packs (sanity check)
    overlap = [sid for sid in candidates if sid in prior_verified]
    lines.append(f"## Sanity overlap — {len(overlap)} of {len(prior_verified)} prior-verified senators also appear in starter packs")
    lines.append("")
    discrepancies = []
    for sid in overlap:
        gov = prior_verified[sid].lower()
        pack_handles = {c["handle"] for c in out_candidates[sid]}
        if gov and gov not in pack_handles:
            discrepancies.append((sid, gov, sorted(pack_handles)))
    if discrepancies:
        lines.append(f"**{len(discrepancies)} senators where .gov-linked handle differs from pack handle:**")
        lines.append("")
        for sid, gov, pack_handles in discrepancies:
            sen = members_by_id[sid]
            lines.append(f"- {sen['full_name']}: .gov says `{gov}`, packs say {pack_handles}")
        lines.append("")
    else:
        lines.append("No discrepancies. .gov-linked handles match pack-curated handles exactly.")
        lines.append("")

    # Section 5: unmatched
    lines.append(f"## Unmatched pack entries ({len(unmatched)})")
    lines.append("")
    lines.append("Members of the curated packs that don't map to any current senator. Mostly: House members, committees, former members, staff, parody. Useful as a noise floor.")
    lines.append("")
    sample = unmatched[:30]
    for u in sample:
        lines.append(f"- `{u['handle']}` — {u.get('displayName') or '?'} _(in {u['pack']})_")
    if len(unmatched) > len(sample):
        lines.append(f"- ... {len(unmatched) - len(sample)} more")
    lines.append("")

    OUT_MD.write_text("\n".join(lines))
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
