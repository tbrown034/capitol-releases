"""
Promote House RSS-eligible members in pipeline/seeds/house.json.

Reads the swap-eligible list from pipeline/recon/house_rss_probe.json and
updates the matching member records in house.json so they are picked up
by the daily collector path. Members not in the swap-eligible list are
left untouched (their collection_method stays null and they are skipped
by update.py until a later wave promotes them).

Idempotent: rerunning with the same probe results in no diff.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PROBE_FILE = ROOT / "pipeline" / "recon" / "house_rss_probe.json"
SEED_FILE = ROOT / "pipeline" / "seeds" / "house.json"


def main():
    probe = json.loads(PROBE_FILE.read_text())
    eligible = {
        r["member_id"]: r["best_feed_url"]
        for r in probe["results"]
        if r.get("swap_eligible") and r.get("best_feed_url")
    }
    print(f"Probe lists {len(eligible)} swap-eligible House members")

    seed = json.loads(SEED_FILE.read_text())
    members = seed["members"]
    promoted = 0
    already = 0
    for m in members:
        mid = m["member_id"]
        if mid not in eligible:
            continue
        feed_url = eligible[mid]
        if (
            m.get("collection_method") == "rss"
            and m.get("rss_feed_url") == feed_url
            and m.get("recon_status") == "verified"
        ):
            already += 1
            continue
        m["collection_method"] = "rss"
        m["rss_feed_url"] = feed_url
        m["recon_status"] = "verified"
        m["last_verified"] = "2026-05-02"
        promoted += 1

    SEED_FILE.write_text(json.dumps(seed, indent=2) + "\n")
    print(f"Promoted: {promoted} (already-current: {already})")
    print(f"Wrote {SEED_FILE}")


if __name__ == "__main__":
    main()
