"""
Promote recon-discovered channels into pipeline/seeds/house.json.

Reads pipeline/recon/house_full_recon.json (output of house_full_recon.py)
and updates each member entry in house.json with:

  - press_release_url     (best `press_release`-classified listing)
  - selectors             (from that listing)
  - pagination            (from that listing)
  - parser_family         (senate-drupal / senate-wordpress / senate-generic)
  - last_verified         (today's date)
  - recon_status          ('verified' if a usable listing exists; else
                           'needs_attention')
  - collection_method     (preserved if already 'rss'; set to 'httpx' for
                           members that lack RSS but have a working
                           HTML listing)

For members already on RSS (the 89 from today's first wave), the RSS
config stays in place for daily collection — RSS is faster and more
reliable for daily polling — but their press_release_url + selectors
get filled in so pipeline/backfill.py can deep-crawl them to Jan 2025.

Multi-channel content (op_eds, columns, newsletters, speeches) is NOT
populated into house.json by this script. Those go into a separate
silo list (pipeline/scripts/backfill_silos.py pattern), built after
this initial press-release wave is verified.

Usage:
    python pipeline/scripts/promote_house_channels.py            # dry-run
    python pipeline/scripts/promote_house_channels.py --apply    # write
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RECON_FILE = ROOT / "pipeline" / "recon" / "house_full_recon.json"
SEED_FILE = ROOT / "pipeline" / "seeds" / "house.json"

PARSER_FAMILY_BY_CMS = {
    "drupal": "senate-drupal",
    "wordpress": "senate-wordpress",
    "coldfusion": "senate-coldfusion",
    "custom": "senate-generic",
    "unreachable": "senate-generic",
}


def url_specificity(url: str) -> int:
    """Higher = more specific. Used to break ties between overlapping URLs."""
    path = url.split("//", 1)[-1].split("/", 1)
    if len(path) < 2:
        return 0
    return path[1].count("/") + (1 if "press-release" in path[1] else 0)


def pick_best_press_release_listing(channels: list[dict]) -> dict | None:
    """Among a member's channels, pick the best press_release listing.

    Selection order:
      1. Must be is_listing=True and not rejected.
      2. content_type == 'press_release' preferred over 'statement' /
         unclassified.
      3. Prefer ones with pagination configured.
      4. Tie-break by URL specificity (more nested path wins, and any
         URL containing 'press-release' wins over generic 'media-center').
    """
    usable = [
        c for c in channels
        if c.get("is_listing") and not c.get("rejected") and c.get("status_code") == 200
    ]
    if not usable:
        return None

    def score(c: dict) -> tuple[int, int, int]:
        ct_score = 2 if c.get("content_type") == "press_release" else (1 if c.get("content_type") in ("statement", None) else 0)
        pag_score = 1 if c.get("pagination") else 0
        return (ct_score, pag_score, url_specificity(c["url"]))

    usable.sort(key=score, reverse=True)
    best = usable[0]
    # Only return if the winner is actually classified as press_release or
    # unclassified-but-paginated. Don't promote an op-ed listing as the
    # member's press_release_url.
    if best.get("content_type") and best["content_type"] not in (
        "press_release",
        None,
        "statement",
    ):
        return None
    return best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write house.json. Without this, prints a diff report.",
    )
    args = parser.parse_args()

    if not RECON_FILE.exists():
        raise SystemExit(
            f"{RECON_FILE} not found. Run pipeline/recon/house_full_recon.py first."
        )

    recon = json.loads(RECON_FILE.read_text())
    seed = json.loads(SEED_FILE.read_text())

    recon_by_id = {r["member_id"]: r for r in recon["results"]}

    today = date.today().isoformat()

    promoted = 0
    needs_attention = 0
    unchanged = 0
    by_family: Counter[str] = Counter()

    for m in seed["members"]:
        mid = m["member_id"]
        r = recon_by_id.get(mid)
        if not r:
            continue
        cms = r.get("cms_family") or "custom"
        family = PARSER_FAMILY_BY_CMS.get(cms, "senate-generic")

        best = pick_best_press_release_listing(r.get("channels", []))
        if not best:
            # Mark for manual triage
            if m.get("recon_status") != "needs_attention":
                m["recon_status"] = "needs_attention"
                needs_attention += 1
            continue

        new_press_url = best["url"]
        new_selectors = best.get("selectors") or {}
        new_pagination = best.get("pagination")

        is_changed = (
            m.get("press_release_url") != new_press_url
            or m.get("selectors") != new_selectors
            or m.get("pagination") != new_pagination
            or m.get("parser_family") != family
        )

        if is_changed:
            m["press_release_url"] = new_press_url
            m["selectors"] = new_selectors
            if new_pagination:
                m["pagination"] = new_pagination
            m["parser_family"] = family
            m["last_verified"] = today
            m["recon_status"] = "verified"
            # Only set collection_method='httpx' if member doesn't already
            # have a working RSS feed. Preserve 'rss' for daily reliability;
            # backfill uses press_release_url regardless of collection_method.
            if not m.get("collection_method"):
                m["collection_method"] = "httpx"
            promoted += 1
        else:
            unchanged += 1
        by_family[family] += 1

    print(f"Recon members: {len(recon_by_id)}")
    print(f"Promoted: {promoted}")
    print(f"Needs attention (no usable listing): {needs_attention}")
    print(f"Unchanged: {unchanged}")
    print("\nFamily distribution among promoted:")
    for fam, n in by_family.most_common():
        print(f"  {fam:<22} {n}")

    if args.apply:
        SEED_FILE.write_text(json.dumps(seed, indent=2) + "\n")
        print(f"\nWrote {SEED_FILE}")
    else:
        print("\nDry-run. Pass --apply to write house.json.")


if __name__ == "__main__":
    main()
