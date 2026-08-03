"""
Build a mapping of House member slugs (member_id in pipeline/seeds/house.json) to
Library of Congress bioguide_id values.

Source: unitedstates/congress-legislators (the canonical open dataset of
legislator IDs maintained collaboratively by Sunlight, GovTrack, ProPublica,
the New York Times, and others). bioguide.congress.gov itself is Cloudflare-
protected and refuses non-browser scraping (verified 2026-05-02), so we use
the GitHub-hosted YAML as the canonical mirror.

Strategy:
  1. Load /tmp/legis.yaml (current) and /tmp/legis_hist.yaml (historical) for
     names like "Joe Smith was just sworn in last week and isn't current yet"
     fallbacks.
  2. Build candidate index keyed on (state, last-name lower) with all reps
     who served in the 119th Congress (term covering 2025-2027).
  3. For each member in pipeline/seeds/house.json, match by:
        a. (state, district) exact -- strongest signal for current reps
        b. (state, last-name) exact among 119th Congress reps
        c. (state, last-name fuzzy / normalized first-name) for nicknames
  4. Write pipeline/recon/house_bioguide_ids.json.

No live network calls in this script -- it operates on the YAML snapshots.
The fetch step happens once via curl in the surrounding shell.
"""

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path("/Users/home/Desktop/dev/active/capitol-releases")
HOUSE_JSON = ROOT / "pipeline/seeds/house.json"
OUT_JSON = ROOT / "pipeline/recon/house_bioguide_ids.json"

LEGIS_CURRENT = Path("/tmp/legis.yaml")
LEGIS_HIST = Path("/tmp/legis_hist.yaml")


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def norm(s: str) -> str:
    s = strip_accents(s or "").lower()
    s = re.sub(r"[\.\,\'\"]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Common nicknames -> formal first names (and vice versa). Bidirectional.
NICK_PAIRS = [
    ("bob", "robert"),
    ("rob", "robert"),
    ("bobby", "robert"),
    ("bill", "william"),
    ("billy", "william"),
    ("will", "william"),
    ("liz", "elizabeth"),
    ("beth", "elizabeth"),
    ("betsy", "elizabeth"),
    ("jim", "james"),
    ("jimmy", "james"),
    ("jamie", "james"),
    ("mike", "michael"),
    ("mick", "michael"),
    ("dave", "david"),
    ("dan", "daniel"),
    ("danny", "daniel"),
    ("tom", "thomas"),
    ("tommy", "thomas"),
    ("rick", "richard"),
    ("dick", "richard"),
    ("rich", "richard"),
    ("chris", "christopher"),
    ("nick", "nicholas"),
    ("nicky", "nicholas"),
    ("tony", "anthony"),
    ("ant", "anthony"),
    ("ed", "edward"),
    ("eddie", "edward"),
    ("ted", "edward"),
    ("ted", "theodore"),
    ("matt", "matthew"),
    ("greg", "gregory"),
    ("ben", "benjamin"),
    ("benny", "benjamin"),
    ("sam", "samuel"),
    ("sammy", "samuel"),
    ("alex", "alexander"),
    ("al", "albert"),
    ("al", "alfred"),
    ("steve", "steven"),
    ("steve", "stephen"),
    ("kate", "katherine"),
    ("kathy", "katherine"),
    ("kathie", "katherine"),
    ("katie", "katherine"),
    ("kate", "kathleen"),
    ("pat", "patrick"),
    ("patty", "patricia"),
    ("trish", "patricia"),
    ("ron", "ronald"),
    ("ronnie", "ronald"),
    ("don", "donald"),
    ("donny", "donald"),
    ("andy", "andrew"),
    ("drew", "andrew"),
    ("joe", "joseph"),
    ("joey", "joseph"),
    ("john", "jonathan"),
    ("jack", "john"),
    ("johnny", "john"),
    ("frank", "francis"),
    ("frankie", "francis"),
    ("hank", "henry"),
    ("harry", "henry"),
    ("ken", "kenneth"),
    ("kenny", "kenneth"),
    ("larry", "lawrence"),
    ("larry", "laurence"),
    ("nate", "nathan"),
    ("nat", "nathaniel"),
    ("phil", "philip"),
    ("phil", "phillip"),
    ("ray", "raymond"),
    ("russ", "russell"),
    ("vince", "vincent"),
    ("zach", "zachary"),
    ("abby", "abigail"),
    ("maggie", "margaret"),
    ("peggy", "margaret"),
    ("meg", "margaret"),
    ("vicky", "victoria"),
    ("vic", "victor"),
    ("debbie", "deborah"),
    ("deb", "deborah"),
    ("debby", "debra"),
    ("deb", "debra"),
    ("jen", "jennifer"),
    ("jenny", "jennifer"),
    ("jeff", "jeffrey"),
    ("jerry", "gerald"),
    ("jerry", "gerard"),
    ("nick", "nicolas"),
    ("eric", "erik"),
    ("erik", "eric"),
]


def first_name_variants(first: str) -> set[str]:
    f = norm(first)
    out = {f}
    for a, b in NICK_PAIRS:
        if f == a:
            out.add(b)
        if f == b:
            out.add(a)
    return out


def is_119th_term(term: dict) -> bool:
    """A term that overlapped the 119th Congress (Jan 3, 2025 - Jan 3, 2027)."""
    if term.get("type") != "rep":
        return False
    start = term.get("start", "")
    end = term.get("end", "")
    # 119th Congress: noon Jan 3, 2025 -> noon Jan 3, 2027.
    # Outgoing reps' terms end on 2025-01-03, so we need strict > on the end date
    # to avoid pulling 118th-Congress holdovers into the candidate set.
    try:
        return start < "2027-01-03" and end > "2025-01-03"
    except Exception:
        return False


def index_legislators() -> dict:
    """Build lookup tables from the YAML files."""
    index = {
        # (state, last_norm) -> list of {bioguide, first, middle, full, district, end}
        "by_state_last": {},
        # bioguide -> record (for diagnostics)
        "by_bioguide": {},
    }

    for path in (LEGIS_CURRENT, LEGIS_HIST):
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text())
        for m in data:
            ids = m.get("id", {})
            bioguide = ids.get("bioguide")
            if not bioguide:
                continue
            name = m.get("name", {})
            first = name.get("first", "") or ""
            last = name.get("last", "") or ""
            middle = name.get("middle", "") or ""
            nickname = name.get("nickname", "") or ""
            full = name.get("official_full", f"{first} {last}").strip()

            for term in m.get("terms", []):
                if not is_119th_term(term):
                    continue
                state = term.get("state", "")
                district = term.get("district", None)
                end = term.get("end", "")
                rec = {
                    "bioguide": bioguide,
                    "first": first,
                    "last": last,
                    "middle": middle,
                    "nickname": nickname,
                    "full": full,
                    "state": state,
                    "district": district,
                    "term_end": end,
                }
                key = (state, norm(last))
                index["by_state_last"].setdefault(key, []).append(rec)
                index["by_bioguide"][bioguide] = rec
    return index


def parse_seed_name(full_name: str) -> dict:
    """Heuristically split 'Mike D. Rogers' -> first=Mike, middle=D., last=Rogers."""
    parts = full_name.strip().split()
    if not parts:
        return {"first": "", "last": ""}
    if len(parts) == 1:
        return {"first": "", "last": parts[0]}
    # Strip suffixes like Jr., Sr., II, III, IV
    SUFFIX = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}
    suffix = ""
    if parts[-1].lower().rstrip(".") in SUFFIX or parts[-1].lower() in SUFFIX:
        suffix = parts.pop()
    first = parts[0]
    last = parts[-1]
    middle = " ".join(parts[1:-1])
    return {"first": first, "middle": middle, "last": last, "suffix": suffix}


def match_member(seed: dict, index: dict) -> tuple[str | None, str]:
    """Return (bioguide_id_or_None, reason_string)."""
    state = seed.get("state", "").upper()
    seed_district = seed.get("district")
    parsed = parse_seed_name(seed.get("full_name", ""))
    last_norm = norm(parsed["last"])
    seed_first = parsed["first"]
    seed_first_variants = first_name_variants(seed_first)

    candidates = index["by_state_last"].get((state, last_norm), [])

    # Strategy A: state + last-name unique
    if len(candidates) == 1:
        return candidates[0]["bioguide"], "unique state+last"

    if not candidates:
        # Strategy A1: multi-word last names. Seeds like "Bonnie Watson Coleman"
        # get parsed as last="Coleman", but the YAML stores last="Watson Coleman".
        # Try (a) substring search on full_name within state, and (b) last-name
        # ending with the seed's last token.
        seed_full_norm = norm(seed.get("full_name", ""))
        state_matches = []
        for (st, ln), recs in index["by_state_last"].items():
            if st != state:
                continue
            for rec in recs:
                rec_full_norm = norm(rec["full"])
                rec_last_norm = norm(rec["last"])
                # Seed full name contains rec last name as suffix or substring
                if rec_last_norm and rec_last_norm in seed_full_norm:
                    state_matches.append(rec)
                # Or rec full name matches seed full name
                elif rec_full_norm == seed_full_norm:
                    state_matches.append(rec)
        # Dedup by bioguide
        seen = set()
        deduped = []
        for r in state_matches:
            if r["bioguide"] not in seen:
                seen.add(r["bioguide"])
                deduped.append(r)
        if len(deduped) == 1:
            return deduped[0]["bioguide"], "state+multiword-last via fullname"
        if len(deduped) > 1:
            # Disambiguate by district
            seed_dist = seed.get("district")
            if seed_dist is not None:
                seed_dist_str = str(seed_dist).lower()
                seed_dist_int = (
                    0
                    if seed_dist_str in {"at-large", "at large", "0"}
                    else int(seed_dist) if str(seed_dist).isdigit() else None
                )
                if seed_dist_int is not None:
                    dm = [r for r in deduped if r.get("district") == seed_dist_int]
                    if len(dm) == 1:
                        return dm[0]["bioguide"], "state+multiword-last+district"

        # Strategy A2: try without state, search every state for (last_norm)
        all_last = []
        for (st, ln), recs in index["by_state_last"].items():
            if ln == last_norm:
                all_last.extend(recs)
        if len(all_last) == 1:
            return all_last[0]["bioguide"], "unique last-name (no state match)"
        return None, "no candidate with that last name in 119th Congress"

    # Strategy B: state + last + first-name variant match
    matched = []
    for c in candidates:
        c_first_norm = norm(c["first"])
        c_nick_norm = norm(c["nickname"])
        c_variants = first_name_variants(c["first"])
        if c_nick_norm:
            c_variants |= first_name_variants(c["nickname"])
        if seed_first_variants & c_variants:
            matched.append(c)
        elif c_first_norm and (
            c_first_norm.startswith(norm(seed_first))
            or norm(seed_first).startswith(c_first_norm)
        ):
            matched.append(c)

    if len(matched) == 1:
        return matched[0]["bioguide"], "state+last+first-variant"

    # Strategy C: district disambiguation
    if seed_district is not None:
        seed_dist_str = str(seed_district).lower()
        if seed_dist_str in {"at-large", "at large", "0"}:
            seed_dist_int = 0
        else:
            try:
                seed_dist_int = int(seed_district)
            except (ValueError, TypeError):
                seed_dist_int = None
        if seed_dist_int is not None:
            dist_matched = [c for c in candidates if c.get("district") == seed_dist_int]
            if len(dist_matched) == 1:
                return dist_matched[0]["bioguide"], "state+last+district"
            if matched and len(dist_matched) >= 1:
                # Intersect
                inter = [c for c in dist_matched if c in matched]
                if len(inter) == 1:
                    return inter[0]["bioguide"], "state+last+first+district"

    if len(matched) > 1:
        return None, f"ambiguous: {len(matched)} candidates after first-name match"
    return None, f"ambiguous: {len(candidates)} state+last candidates, no first-name variant matched"


def main() -> None:
    house = json.loads(HOUSE_JSON.read_text())
    members = house["members"]
    index = index_legislators()

    print(f"Loaded {len(members)} House seeds")
    print(f"Built index with {len(index['by_bioguide'])} 119th Congress reps")

    mapping: dict[str, str] = {}
    unmatched: list[dict] = []
    reasons: dict[str, int] = {}

    for m in members:
        slug = m["member_id"]
        bioguide, reason = match_member(m, index)
        reasons[reason] = reasons.get(reason, 0) + 1
        if bioguide:
            mapping[slug] = bioguide
        else:
            unmatched.append(
                {
                    "member_id": slug,
                    "full_name": m.get("full_name"),
                    "state": m.get("state"),
                    "district": m.get("district"),
                    "reason": reason,
                }
            )

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "unitedstates/congress-legislators (legislators-current.yaml + legislators-historical.yaml)",
        "matched": len(mapping),
        "total_seeds": len(members),
        "unmatched_count": len(unmatched),
        "unmatched": unmatched,
        "match_reasons": reasons,
        "mapping": dict(sorted(mapping.items())),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2) + "\n")

    print(f"\nMatched: {len(mapping)} / {len(members)}")
    print(f"Unmatched: {len(unmatched)}")
    print("\nMatch reasons:")
    for r, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {r}")
    if unmatched:
        print("\nUnmatched members:")
        for u in unmatched:
            print(f"  {u['member_id']:35s}  {u['full_name']:30s}  {u['state']}-{u['district']}  ({u['reason']})")


if __name__ == "__main__":
    main()
