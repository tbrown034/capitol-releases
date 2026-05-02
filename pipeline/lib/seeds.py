"""Seed loading for Capitol Releases.

Loads member configs from pipeline/seeds/*.json. Each seed file exposes
a `members` list. Every entry returned by load_members() is guaranteed
to carry the structural fields the post-2026-05-02 schema requires:
chamber, jurisdiction, branch, office_type. Defaults are applied only
when an entry doesn't declare its own value.
"""

import json
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent.parent / "seeds"


# Per-file structural defaults. Order matters for some downstream code that
# treats senate.json members as "the canonical Senate roster."
#
# Tuple shape: (filename, defaults dict). defaults are applied only when an
# entry doesn't declare its own value.
#
# branch / jurisdiction / chamber / office_type follow the post-2026-05-02
# normalized schema (migration 012). State legislators sit under
# (chamber=senate|unicameral, jurisdiction=<state code>) — the legacy
# overloaded chamber='tx_senate' / 'ne_unicameral' / etc. values were
# normalized away.
_SEED_FILES: list[tuple[str, dict]] = [
    ("senate.json",        {"branch": "legislative", "jurisdiction": "us", "chamber": "senate",     "office_type": "senator"}),
    ("house.json",         {"branch": "legislative", "jurisdiction": "us", "chamber": "house",      "office_type": "representative"}),
    ("executive.json",     {"branch": "executive",   "jurisdiction": "us", "chamber": None,         "office_type": "executive_office"}),
    ("tx_senate.json",     {"branch": "legislative", "jurisdiction": "tx", "chamber": "senate",     "office_type": "state_senator"}),
    ("ne_unicameral.json", {"branch": "legislative", "jurisdiction": "ne", "chamber": "unicameral", "office_type": "state_senator"}),
    ("ca_senate.json",     {"branch": "legislative", "jurisdiction": "ca", "chamber": "senate",     "office_type": "state_senator"}),
    ("oh_senate.json",     {"branch": "legislative", "jurisdiction": "oh", "chamber": "senate",     "office_type": "state_senator"}),
    ("mo_senate.json",     {"branch": "legislative", "jurisdiction": "mo", "chamber": "senate",     "office_type": "state_senator"}),
    ("wv_legislature.json",{"branch": "legislative", "jurisdiction": "wv", "chamber": "senate",     "office_type": "state_senator"}),
]


def load_members(
    chambers: list[str] | None = None,
    jurisdictions: list[str] | None = None,
    include_unconfigured: bool = False,
) -> list[dict]:
    """Load member configs.

    Args:
        chambers: If given, only return entries whose chamber is in this list.
        jurisdictions: If given, only return entries whose jurisdiction is in
            this list. Use this for "all Texas members" or "all federal
            members" queries.
        include_unconfigured: When False (default), skip members whose
            collection_method is None / missing. House ships with hundreds
            of recon-discovered rows that the collector cannot service yet;
            including them in update.py would spam logs with "no feed url"
            errors. Set True for tooling that needs the full roster (e.g.
            coverage reports, sync scripts that load all rows into the DB).
    """
    members: list[dict] = []
    for filename, defaults in _SEED_FILES:
        path = SEED_DIR / filename
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for m in data.get("members", []):
            for key, value in defaults.items():
                # Only set when the entry doesn't already declare its own.
                # `chamber` may legitimately be None (for executives), so
                # use sentinel-aware setdefault rather than truthiness.
                if key not in m or m[key] is None and value is not None:
                    # Honor explicit nulls by NOT overriding them. If the
                    # default itself is None (executives have no chamber),
                    # set the key only when missing entirely.
                    if key in m and m[key] is None:
                        continue
                    m[key] = value
                # Normalize legacy chamber values that may still live in older
                # seed JSON files (tx_senate, ne_unicameral, etc.). Migration
                # 012 already cleaned the DB; this keeps re-syncs idempotent.
            legacy = m.get("chamber")
            if legacy in ("tx_senate", "ca_senate", "oh_senate", "mo_senate",
                          "wv_legislature"):
                m["chamber"] = "senate"
            elif legacy == "ne_unicameral":
                m["chamber"] = "unicameral"
            elif legacy == "executive":
                m["chamber"] = None
                m.setdefault("branch", "executive")

            # House members carry member_id; the rest of the pipeline keys
            # on official_id. Normalize so callers don't special-case.
            if "official_id" not in m and "member_id" in m:
                m["official_id"] = m["member_id"]
            members.append(m)
    if chambers:
        members = [m for m in members if m.get("chamber") in chambers]
    if jurisdictions:
        members = [m for m in members if m.get("jurisdiction") in jurisdictions]
    if not include_unconfigured:
        members = [m for m in members if m.get("collection_method")]
    return members
