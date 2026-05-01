"""Promote recon results into pipeline/seeds/bluesky_handles.json.

Combines two evidence sources:

  1. bluesky_recon_results.json — handles linked from a senator's official
     senate.gov pages (gold-standard verification per AT Protocol's
     domain-handle convention).
  2. bluesky_starterpack_xref.json — handles found in 2+ curated public
     starter packs with match score ≥0.75.

For each senator we keep at most one handle, preferring (in order):
  a. Handle that lives at <senator>.senate.gov regardless of source
  b. Handle linked from senate.gov (any host)
  c. Handle confirmed by ≥2 starter packs, score ≥0.75

Every entry carries provenance: which evidence stream confirmed it,
the URL or pack list, and the confirmation date.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECON = ROOT / "pipeline" / "recon" / "bluesky_recon_results.json"
XREF = ROOT / "pipeline" / "recon" / "bluesky_starterpack_xref.json"
OUT = ROOT / "pipeline" / "seeds" / "bluesky_handles.json"

# Manual review notes attached to specific senators.
NOTES: dict[str, str] = {
    "rosen-jacky": (
        "senate.gov footer points to rosen.senate.gov; some packs list "
        "senatorjackyrosen.bsky.social. Adopting the .gov-linked official; "
        "the bsky.social variant may be a campaign account."
    ),
    "klobuchar-amy": (
        "amyklobuchar.com is her own domain (acceptable handle verification "
        "per AT Protocol). Confirmed by 4 independent starter packs."
    ),
    "kelly-mark": (
        "captmarkkelly.bsky.social — appears in 2 packs. Verify against "
        "his .gov-linked socials before promoting to high confidence."
    ),
    "schatz-brian": (
        "schatz.bsky.social — appears in 6 packs. No senate.gov link, but "
        "consensus across curators is strong."
    ),
}


def main() -> None:
    recon = json.loads(RECON.read_text())["results"]
    xref = json.loads(XREF.read_text())["candidates_by_senator"]

    today = date.today().isoformat()
    handles: list[dict] = []

    # Pass 1 — senate.gov-linked handles
    gov_seen: set[str] = set()
    for r in recon:
        sid = r["senator_id"]
        enriched = r.get("site_handles_enriched") or []
        if not enriched:
            continue
        h = enriched[0]
        gov_seen.add(sid)
        handles.append({
            "senator_id": sid,
            "handle": h["handle"],
            "did": h.get("did"),
            "verified_via": h.get("verified_via", "senate.gov footer"),
            "verified_at": today,
            "confidence": "gov_link",
            "display_name": h.get("display_name"),
            "followers_at_verification": h.get("followers"),
            "posts_total_at_verification": h.get("posts_total"),
            "notes": NOTES.get(sid),
        })

    # Pass 2 — starter-pack-confirmed handles for senators not in gov_seen
    for sid, candidates in xref.items():
        if sid in gov_seen:
            continue
        if not candidates:
            continue
        best = candidates[0]
        # Promotion bar: must clear at least one of:
        #   (a) handle host is <something>.senate.gov  → unambiguous official
        #   (b) ≥2 packs AND score ≥0.75              → multi-curator consensus
        is_gov_handle = best["handle"].endswith(".senate.gov")
        meets_consensus = best["pack_count"] >= 2 and best["match_score"] >= 0.75
        if not (is_gov_handle or meets_consensus):
            continue
        handles.append({
            "senator_id": sid,
            "handle": best["handle"],
            "did": best.get("did"),
            "verified_via": (
                "senate.gov-domain handle (no footer link)" if is_gov_handle
                else f"starter packs ({best['pack_count']}): " + "; ".join(best["packs"])
            ),
            "verified_at": today,
            "confidence": "gov_handle" if is_gov_handle else "pack_consensus",
            "display_name": best.get("displayName"),
            "match_score": best["match_score"],
            "pack_count": best["pack_count"],
            "notes": NOTES.get(sid),
        })

    handles.sort(key=lambda h: h["senator_id"])

    out_doc = {
        "_meta": {
            "description": (
                "Senator → verified Bluesky handle mapping. Every entry was "
                "confirmed via at least one of: (1) a link on the senator's "
                "senate.gov site, (2) the handle living at a senate.gov "
                "subdomain, or (3) appearance in two or more independent "
                "curated starter packs with name-match score ≥0.75."
            ),
            "verification_priority": "gov_link > gov_handle > pack_consensus",
            "generated_by": "pipeline.recon.build_bluesky_seeds",
            "generated_at": today,
            "schema": {
                "senator_id": "matches senators.id",
                "handle": "Bluesky handle without @",
                "did": "AT Protocol DID (did:plc:...)",
                "verified_via": "evidence: URL, 'senate.gov footer', or pack list",
                "verified_at": "ISO date of confirmation",
                "confidence": "gov_link | gov_handle | pack_consensus",
                "notes": "free text, optional",
            },
        },
        "handles": handles,
    }

    OUT.write_text(json.dumps(out_doc, indent=2))

    # Summary
    by_conf: dict[str, int] = {}
    for h in handles:
        by_conf[h["confidence"]] = by_conf.get(h["confidence"], 0) + 1
    print(f"Wrote {len(handles)} handles to {OUT.relative_to(ROOT)}")
    for k, v in sorted(by_conf.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
