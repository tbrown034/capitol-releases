"""Stitch agent JSONs into the master inventory and CSV.

Reads raw/*.json from sub-agent runs and writes:
  - inventory.json (unified)
  - inventory.csv  (machine-readable)
  - first_10.json (top 10 ready-first-wave by confidence)
  - do_not_implement.json
"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
RAW = ROOT / "raw"
OUT = ROOT


def load_all():
    sources = []
    for path in sorted(RAW.glob("*.json")):
        try:
            d = json.loads(path.read_text())
        except Exception as e:
            print(f"[warn] could not parse {path.name}: {e}")
            continue
        items = d.get("sources", [])
        # us_house.json uses "members" + a "profile"
        if not items and "members" in d:
            items = d.get("members", [])
        # selector_deep_dive uses "sources" too — already handled
        # browser_render uses "sites" — load separately for evidence, not main inventory
        if not items and "sites" in d:
            items = d.get("sites", [])
        for s in items:
            s["_origin_file"] = path.name
            sources.append(s)
    return sources


CSV_FIELDS = [
    "state",
    "level",
    "office_or_chamber",
    "party",
    "official_url",
    "press_listing_url",
    "roster_url",
    "detail_url_pattern",
    "cms_family",
    "requires_js",
    "pagination",
    "feed_rss",
    "feed_wp_json",
    "post_frequency_estimate",
    "scraping_strategy",
    "attribution_strategy",
    "classification",
    "confidence",
    "weird_risks",
    "_origin_file",
]


def normalize(s: dict) -> dict:
    """Map heterogeneous agent records to a uniform shape."""
    chamber = s.get("chamber") or s.get("office") or s.get("office_or_chamber")
    party = s.get("party")
    is_legislature = chamber in ("senate", "house", "unicameral", "assembly")
    is_caucus = bool(s.get("_origin_file") and "caucus" in s.get("_origin_file"))
    if is_caucus:
        level = "caucus"
        office_label = f"{chamber}_{party or 'X'}_caucus"
    elif chamber == "us-house" or s.get("_origin_file") == "us_house.json":
        level = "us_house"
        office_label = "us_house_member"
    elif is_legislature:
        level = "legislature"
        office_label = chamber
    else:
        level = "executive"
        office_label = chamber
    out = {
        "state": s.get("state"),
        "level": level,
        "office_or_chamber": office_label,
        "party": party,
        "incumbent_name": s.get("incumbent_name"),
        "official_url": s.get("official_chamber_url") or s.get("official_url"),
        "press_listing_url": s.get("press_listing_url"),
        "roster_url": s.get("roster_url"),
        "detail_url_pattern": s.get("detail_url_pattern"),
        "member_press_url_pattern": s.get("member_press_url_pattern"),
        "sample_member_press_urls": s.get("sample_member_press_urls", []),
        "sample_release_urls": s.get("sample_release_urls", []),
        "cms_family": s.get("cms_family"),
        "requires_js": s.get("requires_js"),
        "pagination": s.get("pagination"),
        "feed_rss": s.get("feed_rss"),
        "feed_atom": s.get("feed_atom"),
        "feed_wp_json": s.get("feed_wp_json"),
        "content_shapes": s.get("content_shapes", []),
        "post_frequency_estimate": s.get("post_frequency_estimate"),
        "scraping_strategy": s.get("scraping_strategy"),
        "attribution_strategy": s.get("attribution_strategy"),
        "classification": s.get("classification"),
        "confidence": s.get("confidence"),
        "weird_risks": s.get("weird_risks"),
        "evidence": s.get("evidence", {}),
        "_origin_file": s.get("_origin_file"),
    }
    return out


def main():
    sources = load_all()
    if not sources:
        print("No sources loaded — agents may not have written JSONs yet")
        return
    print(f"Loaded {len(sources)} raw source records")

    rows = [normalize(s) for s in sources]

    # Skip the US House per-member member records from the main inventory dedup;
    # they're profiled in a separate file. Keep one summary row.
    house_rows = [r for r in rows if r.get("level") == "us_house"]
    other_rows = [r for r in rows if r.get("level") != "us_house"]

    seen = set()
    deduped = []
    for r in other_rows:
        key = (r.get("state"), r.get("office_or_chamber"), r.get("party"), r.get("official_url"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    # Add a single summary row for US House
    if house_rows:
        deduped.append({
            "state": "US",
            "level": "us_house",
            "office_or_chamber": "us_house_member",
            "official_url": "https://www.house.gov/representatives",
            "press_listing_url": None,
            "cms_family": "drupal_house_hmwp_majority",
            "requires_js": False,
            "scraping_strategy": "playwright_or_browser_headers_httpx",
            "classification": "needs_profile",
            "confidence": 0.7,
            "weird_risks": "Akamai WAF blocks raw HTTP; need browser-class fetch or rotating residential proxy",
            "evidence": {"member_count": len(house_rows), "checked_at": "2026-05-01"},
            "_origin_file": "us_house.json",
        })

    print(f"Deduped to {len(deduped)} unique source records (+ {len(house_rows)} US House members in separate file)")

    # Sort: legislatures first by state, then executive
    deduped.sort(key=lambda r: (r.get("level"), r.get("state") or "", r.get("office_or_chamber") or ""))

    # JSON
    (OUT / "inventory.json").write_text(json.dumps(deduped, indent=2, default=str))

    # CSV
    with (OUT / "inventory.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in deduped:
            row = {k: r.get(k) for k in CSV_FIELDS}
            w.writerow(row)

    # Counts
    print()
    print("Counts by classification:")
    for k, v in Counter(r.get("classification") for r in deduped).most_common():
        print(f"  {str(k):35} {v}")
    print()
    print("Counts by level:")
    for k, v in Counter(r.get("level") for r in deduped).most_common():
        print(f"  {str(k):35} {v}")
    print()
    print("Counts by cms_family:")
    for k, v in Counter(r.get("cms_family") for r in deduped).most_common():
        print(f"  {str(k):35} {v}")

    # First 10 = top ready_first_wave by confidence
    rfw = [r for r in deduped if r.get("classification") == "ready_first_wave"]
    rfw.sort(key=lambda r: -(r.get("confidence") or 0))
    first_10 = rfw[:10]
    (OUT / "first_10.json").write_text(json.dumps(first_10, indent=2, default=str))
    print(f"\nFirst 10 ready_first_wave: {len(first_10)} records")
    for r in first_10:
        print(f"  {r['state']:3} {r['office_or_chamber']:20} {r.get('confidence')} {r.get('press_listing_url')}")

    # Do not implement
    dni = [r for r in deduped if r.get("classification") in ("do_not_claim_member_coverage",)]
    (OUT / "do_not_implement.json").write_text(json.dumps(dni, indent=2, default=str))
    print(f"\nDo-not-implement: {len(dni)} records")


if __name__ == "__main__":
    main()
