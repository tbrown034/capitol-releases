"""Seed loading for Capitol Releases.

Loads member configs from pipeline/seeds/*.json. Each seed file exposes
a `members` list. Every entry returned by load_members() is guaranteed
to carry a `chamber` field.
"""

import json
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent.parent / "seeds"

# Tuple of (filename, default_chamber). default_chamber is applied only
# when an entry doesn't declare its own chamber.
_SEED_FILES = [
    ("senate.json", "senate"),
    ("house.json", "house"),
    ("executive.json", "executive"),
    ("tx_senate.json", "tx_senate"),
    ("ne_unicameral.json", "ne_unicameral"),
    ("ca_senate.json", "ca_senate"),
    ("oh_senate.json", "oh_senate"),
    ("mo_senate.json", "mo_senate"),
    ("wv_legislature.json", "wv_legislature"),
]


def load_members(
    chambers: list[str] | None = None,
    include_unconfigured: bool = False,
) -> list[dict]:
    """Load member configs.

    Args:
        chambers: If given, only return entries whose chamber is in this list.
        include_unconfigured: When False (default), skip members whose
            collection_method is None / missing. House ships with hundreds
            of recon-discovered rows that the collector cannot service yet;
            including them in update.py would spam logs with "no feed url"
            errors. Set True for tooling that needs the full roster (e.g.
            coverage reports, sync scripts that load all rows into the DB).
    """
    members: list[dict] = []
    for filename, default_chamber in _SEED_FILES:
        path = SEED_DIR / filename
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for m in data.get("members", []):
            m.setdefault("chamber", default_chamber)
            # House members carry member_id; the rest of the pipeline keys
            # on senator_id. Normalize so callers don't special-case.
            if "senator_id" not in m and "member_id" in m:
                m["senator_id"] = m["member_id"]
            members.append(m)
    if chambers:
        members = [m for m in members if m.get("chamber") in chambers]
    if not include_unconfigured:
        members = [m for m in members if m.get("collection_method")]
    return members
