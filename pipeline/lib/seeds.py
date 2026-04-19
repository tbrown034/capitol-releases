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
    ("executive.json", "executive"),
]


def load_members(chambers: list[str] | None = None) -> list[dict]:
    """Load member configs.

    Args:
        chambers: If given, only return entries whose chamber is in this list.
    """
    members: list[dict] = []
    for filename, default_chamber in _SEED_FILES:
        path = SEED_DIR / filename
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for m in data.get("members", []):
            m.setdefault("chamber", default_chamber)
            members.append(m)
    if chambers:
        members = [m for m in members if m.get("chamber") in chambers]
    return members
