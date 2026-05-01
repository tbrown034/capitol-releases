"""
Senate roll-call vote lookups via the official Congress.gov API.

Activates only when CONGRESS_API_KEY is set in the environment. Without
a key, fetch_senate_votes_for_day() returns an empty list and the brief
runs without scheduled-vote context — exactly the behavior we had before.

Get a key (free): https://api.congress.gov/sign-up/
"""

from __future__ import annotations

import logging
import os
from datetime import date

log = logging.getLogger("capitol.votes")

API_BASE = "https://api.congress.gov/v3"
CURRENT_CONGRESS = 119  # 2025-2027


def fetch_senate_votes_for_day(target_day: date) -> list[dict]:
    """Return roll-call votes that occurred on the ET calendar day target_day.

    Each item: {vote_number, question, result, date}. Empty list on any
    failure (missing key, network error, malformed response, etc.) — the
    brief tolerates absent vote data.
    """
    api_key = os.environ.get("CONGRESS_API_KEY")
    if not api_key:
        log.debug("CONGRESS_API_KEY unset — skipping vote lookup")
        return []

    try:
        import httpx
    except ImportError:
        log.debug("httpx not installed — skipping vote lookup")
        return []

    # Senate session 1 = odd year (2025), session 2 = even year (2026).
    session = 2 if target_day.year % 2 == 0 else 1
    url = f"{API_BASE}/senate-vote/{CURRENT_CONGRESS}/{session}"
    params = {
        "api_key": api_key,
        "format": "json",
        "limit": 50,
    }
    try:
        resp = httpx.get(url, params=params, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("Vote lookup failed: %s", e)
        return []

    votes = data.get("senateVotes") or data.get("votes") or []
    out: list[dict] = []
    iso = target_day.isoformat()
    for v in votes:
        date_str = (v.get("date") or "")[:10]
        if date_str != iso:
            continue
        out.append({
            "vote_number": v.get("voteNumber") or v.get("rollNumber"),
            "question": v.get("question") or v.get("voteQuestion"),
            "result": v.get("result") or v.get("voteResult"),
            "date": date_str,
        })
    return out
