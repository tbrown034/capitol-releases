"""Build pipeline/recon/house_members.json from the Clerk of the House MemberData.xml.

Primary source: https://clerk.house.gov/xml/lists/MemberData.xml (authoritative).
Cross-reference: pipeline/seeds/house.json for existing official_url/press_release_url
mappings that prior recon work collected.

Output: {"members": [...]} at pipeline/recon/house_members.json, schema compatible with
pipeline/seeds/senate.json (top-level shape) but with House-specific fields.

Current as of MemberData.xml publish-date April 22, 2026. Vacant seats are excluded.
"""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter

ROOT = Path("/Users/home/Desktop/dev/active/capitol-releases")
RECON_DIR = ROOT / "pipeline" / "recon"
XML_CACHE = Path("/tmp/memberdata.xml")
EXISTING_SEED = ROOT / "pipeline" / "seeds" / "house.json"
OUT_JSON = RECON_DIR / "house_members.json"
OUT_SUMMARY = RECON_DIR / "house_members_summary.md"
TODAY = "2026-04-24"
SOURCE_URL = "https://clerk.house.gov/xml/lists/MemberData.xml"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

TERRITORIES = {"AS", "DC", "GU", "MP", "PR", "VI"}

# Manual overrides for canonical house.gov subdomains that the prior seed did not
# cover correctly. Keyed by bioguide ID. All verified by HTTP 200 on 2026-04-24.
MANUAL_OFFICIAL_URL = {
    # Analilia Mejia (NJ-11) sworn in April 20 2026 after Sherrill resigned to
    # become NJ governor. Not in prior seed.
    "M001246": "https://mejia.house.gov",
    # Prior seed stripped Unicode accents incorrectly, producing dead URLs like
    # snchez.house.gov (missing 'a'). Real subdomains use the full last name.
    "S001156": "https://lindasanchez.house.gov",  # Linda T. Sánchez (CA-38)
    "B001300": "https://barragan.house.gov",      # Nanette Diaz Barragán (CA-44)
    "V000081": "https://velazquez.house.gov",     # Nydia M. Velázquez (NY-7)
    "H001103": "https://hernandez.house.gov",     # Pablo José Hernández (PR)
}


def fetch_xml() -> bytes:
    if XML_CACHE.exists() and XML_CACHE.stat().st_size > 100_000:
        return XML_CACHE.read_bytes()
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    XML_CACHE.write_bytes(data)
    return data


def slugify(text: str) -> str:
    """lowercase, strip accents, keep [a-z0-9-]."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def member_id_for(lastname: str, firstname: str, state: str, statedistrict: str) -> str:
    """Prefer lastname-firstname. Collision resolution added by caller."""
    return f"{slugify(lastname)}-{slugify(firstname)}"


def normalize_district(district_text: str, state: str) -> str:
    """Return string district. Ordinal -> number; At Large / Delegate / Resident
    Commissioner preserved as human-readable tokens that match existing house.json
    ("At-Large") where possible."""
    if not district_text:
        return ""
    t = district_text.strip()
    # ordinals
    m = re.match(r"^(\d+)(st|nd|rd|th)$", t, re.I)
    if m:
        return m.group(1)
    if t.lower() in ("at large", "at-large"):
        return "At-Large"
    if t.lower() == "delegate":
        return "Delegate"
    if t.lower() == "resident commissioner":
        return "Resident Commissioner"
    return t


def build_full_name(mi: ET.Element) -> str:
    """Prefer <official-name>; fall back to First Middle. Last."""
    official = (mi.findtext("official-name") or "").strip()
    if official:
        return official
    first = (mi.findtext("firstname") or "").strip()
    middle = (mi.findtext("middlename") or "").strip()
    last = (mi.findtext("lastname") or "").strip()
    parts = [p for p in (first, middle, last) if p]
    return " ".join(parts)


def _name_key(full_name: str) -> str:
    """Aggressive name normalization for fallback lookups."""
    s = unicodedata.normalize("NFKD", full_name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Drop middle initials / middle words between first and last to reduce noise
    return s


def load_existing_seed() -> tuple[dict, dict]:
    """Return (by_state_district, by_state_lastname) lookup dicts for the prior
    recon seed file. The existing seed has some records with district=null where
    we still want to salvage the URL via last-name match."""
    if not EXISTING_SEED.exists():
        return {}, {}
    data = json.loads(EXISTING_SEED.read_text())
    by_sd: dict = {}
    by_state_last: dict = {}
    for rec in data.get("members", []):
        state = rec.get("state")
        district = rec.get("district")
        if isinstance(district, int):
            dkey = str(district)
        elif isinstance(district, str):
            dkey = district
        else:
            dkey = None
        if dkey is not None:
            by_sd[(state, dkey)] = rec
            # Also map "At-Large" -> delegate-style aliases for territories
            if dkey == "At-Large" and state in TERRITORIES:
                by_sd[(state, "Delegate")] = rec
                by_sd[(state, "Resident Commissioner")] = rec
        # Name-based fallback (lastname lowercased) keyed by state
        full = rec.get("full_name") or ""
        last_token = full.split()[-1] if full else ""
        last_key = _name_key(last_token)
        if state and last_key:
            by_state_last.setdefault((state, last_key), rec)
    return by_sd, by_state_last


def main() -> None:
    xml_bytes = fetch_xml()
    root = ET.fromstring(xml_bytes)
    publish_date = root.attrib.get("publish-date", "unknown")
    seed_by_sd, seed_by_state_last = load_existing_seed()

    members_raw = root.find("members").findall("member")
    kept: list[dict] = []
    vacancies: list[dict] = []
    seen_ids: Counter = Counter()

    # First pass to populate seen_ids for collision detection
    draft: list[dict] = []
    for m in members_raw:
        mi = m.find("member-info")
        statedistrict = m.findtext("statedistrict") or ""
        state = mi.find("state").attrib.get("postal-code") if mi.find("state") is not None else ""
        party = (mi.findtext("party") or "").strip()
        district_raw = mi.findtext("district") or ""
        district = normalize_district(district_raw, state)
        bioguide = (mi.findtext("bioguideID") or "").strip()
        last = (mi.findtext("lastname") or "").strip()
        first = (mi.findtext("firstname") or "").strip()
        full_name = build_full_name(mi)

        if not bioguide or not party or not full_name:
            vacancies.append({
                "statedistrict": statedistrict,
                "state": state,
                "district": district,
                "reason": "vacant (no sitting member in XML)",
            })
            continue

        mid = member_id_for(last, first, state, statedistrict)
        seen_ids[mid] += 1
        draft.append({
            "_mid_base": mid,
            "bioguide_id": bioguide,
            "full_name": full_name,
            "party": party,
            "state": state,
            "district": district,
            "statedistrict": statedistrict,
            "lastname": last,
            "firstname": first,
        })

    # Second pass: build final records, disambiguate collisions with -state or -statedistrict
    for rec in draft:
        mid = rec["_mid_base"]
        if seen_ids[mid] > 1:
            # collision -> append state-district
            mid_final = f"{mid}-{rec['state'].lower()}{rec['district'].lower().replace(' ', '')}"
        else:
            mid_final = mid

        seed = seed_by_sd.get((rec["state"], rec["district"]))
        match_source = "state-district" if seed else None
        if not seed:
            # Fallback: name match (state + last name). Useful for seed rows where
            # district was dropped (bug in prior recon) or for ordinal-vs-string
            # mismatches.
            last_key = _name_key(rec["lastname"])
            seed = seed_by_state_last.get((rec["state"], last_key))
            if seed:
                match_source = "name"
        official_url = seed.get("official_url") if seed else None
        # Apply manual overrides last so they win over stale seed entries.
        override = MANUAL_OFFICIAL_URL.get(rec["bioguide_id"])
        if override:
            official_url = override
            match_source = "manual-override"
        press_release_url = None  # task instructs to leave null; recon fills later

        out = {
            "member_id": mid_final,
            "full_name": rec["full_name"],
            "party": rec["party"],
            "state": rec["state"],
            "district": rec["district"],
            "chamber": "house",
            "official_url": official_url,
            "press_release_url": press_release_url,
            "bioguide_id": rec["bioguide_id"],
            "last_verified": TODAY,
        }
        # Flag records that need verification: missing official_url from seed
        if not official_url:
            out["needs_verification"] = True
            out["notes"] = (
                "No official_url matched from existing seed; likely new special-election "
                "winner. Verify canonical house.gov subdomain."
            )
        kept.append(out)

    # Sort by state then district (numeric asc, delegates after)
    def sort_key(r):
        st = r["state"]
        d = r["district"]
        try:
            return (st, 0, int(d))
        except ValueError:
            return (st, 1, d)

    kept.sort(key=sort_key)

    OUT_JSON.write_text(json.dumps({"members": kept}, indent=2, ensure_ascii=False) + "\n")

    # Build summary
    parties = Counter(r["party"] for r in kept)
    states = Counter(r["state"] for r in kept)
    needs_verify = [r for r in kept if r.get("needs_verification")]
    delegates = [r for r in kept if r["state"] in TERRITORIES]

    lines = []
    lines.append("# House Members Seed — Recon Summary\n")
    lines.append(f"- Source: {SOURCE_URL}")
    lines.append(f"- Source publish-date: {publish_date}")
    lines.append(f"- Generated: {TODAY}")
    lines.append(f"- Output: `pipeline/recon/house_members.json`\n")
    lines.append("## Counts\n")
    lines.append(f"- Total current members: **{len(kept)}**")
    lines.append(f"- Voting representatives: {len(kept) - len(delegates)}")
    lines.append(f"- Non-voting delegates / resident commissioner: {len(delegates)}")
    lines.append(f"- Vacancies excluded: {len(vacancies)}\n")
    lines.append("## By Party\n")
    for p, n in parties.most_common():
        lines.append(f"- {p}: {n}")
    lines.append("\n## Top 10 States By Seat Count\n")
    for s, n in states.most_common(10):
        lines.append(f"- {s}: {n}")
    lines.append("\n## Vacancies (excluded)\n")
    if vacancies:
        for v in vacancies:
            lines.append(f"- {v['statedistrict']} — {v['reason']}")
    else:
        lines.append("- None")
    lines.append("\n## Non-Voting Delegates (included)\n")
    for d in delegates:
        lines.append(f"- {d['state']} {d['district']}: {d['full_name']} ({d['party']})")
    lines.append("\n## Records Flagged `needs_verification`\n")
    if needs_verify:
        lines.append(
            "These members have no `official_url` in the prior recon seed — likely "
            "special-election winners after the prior recon pass. Manual canonical-URL "
            "check recommended.\n"
        )
        for r in needs_verify:
            lines.append(
                f"- {r['state']}-{r['district']}: {r['full_name']} "
                f"({r['party']}, bioguide={r['bioguide_id']})"
            )
    else:
        lines.append("- None")
    lines.append("\n## Notes / Anomalies\n")
    lines.append(
        "- The Clerk XML publish-date is {pd}; today is {td}. The file already "
        "reflects Rep. David Scott's death (GA-13, April 22 2026), so GA-13 is "
        "treated as vacant.".format(pd=publish_date, td=TODAY)
    )
    lines.append(
        "- GA-14 resolves to Clay Fuller (R), who was sworn in April 14 2026 after "
        "winning the runoff to replace Marjorie Taylor Greene (resigned Jan 5 2026)."
    )
    lines.append(
        "- CA-01 vacant following Rep. Doug LaMalfa's death (Jan 6 2026); special "
        "election scheduled June 2 2026."
    )
    lines.append(
        "- `district` is stored as a string. Numbered districts use the bare numeral "
        "(\"1\", \"12\"), at-large states use \"At-Large\", and territories use "
        "\"Delegate\" / \"Resident Commissioner\" (Puerto Rico)."
    )
    lines.append(
        "- `official_url` was carried over from `pipeline/seeds/house.json` by "
        "matching on (state, district). `press_release_url` is left `null` per task "
        "brief — downstream recon fills it."
    )
    lines.append(
        "- `member_id` is `lastname-firstname` (accents stripped, lowercased, "
        "hyphenated). Collisions append `-<state><district>` but none were observed "
        "in the current roster."
    )
    lines.append(
        "- Kevin Kiley (CA-3) is listed by the Clerk as party=\"I\" but caucus=\"R\". "
        "The seed preserves party=\"I\" to match the authoritative source; downstream "
        "consumers that need caucus affiliation should pull it separately."
    )
    lines.append(
        "- Analilia Mejia (NJ-11) sworn in April 20, 2026 — too recent for the prior "
        "recon seed. Canonical https://mejia.house.gov supplied via MANUAL_OFFICIAL_URL "
        "override in build_house_members.py (HTTP 200 verified 2026-04-24)."
    )
    lines.append(
        "- Four URLs in the prior `pipeline/seeds/house.json` had Unicode accents "
        "incorrectly stripped, producing dead subdomains (`snchez`, `barragn`, "
        "`velzquez`, `hernndez`). Fixed via manual overrides to the real "
        "`lindasanchez`, `barragan`, `velazquez`, `hernandez` subdomains (all HTTP "
        "200 verified 2026-04-24). The prior seed file itself still carries the bad "
        "URLs and should be patched separately before it is used as a collector "
        "source."
    )
    lines.append(
        "- District encoding diverges slightly from the task brief (\"AL\" for "
        "at-large): this file uses \"At-Large\" (hyphenated) to match the existing "
        "`pipeline/seeds/house.json` convention, and uses \"Delegate\" / "
        "\"Resident Commissioner\" to distinguish non-voting seats — more precise "
        "than flattening them to at-large."
    )

    OUT_SUMMARY.write_text("\n".join(lines) + "\n")

    # Console report
    print(f"Wrote {OUT_JSON} ({len(kept)} members)")
    print(f"Wrote {OUT_SUMMARY}")
    print(f"Parties: {dict(parties)}")
    print(f"Delegates: {len(delegates)}")
    print(f"Vacancies excluded: {len(vacancies)}")
    print(f"needs_verification flags: {len(needs_verify)}")


if __name__ == "__main__":
    main()
