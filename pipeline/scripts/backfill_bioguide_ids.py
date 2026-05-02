"""
One-time: populate senators.bioguide_id from theunitedstates/congress-legislators.

Matches db senators against the public legislators-current.json (active
members) and legislators-historical.json (former members, e.g. Rubio,
Vance, Mullin who served during our 2025-onwards window).

Idempotent: will not overwrite existing bioguide_id values.
"""
from __future__ import annotations

import logging
import os
import sys
import unicodedata
from pathlib import Path

import httpx

log = logging.getLogger("backfill_bioguide")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

CURRENT_URL = "https://unitedstates.github.io/congress-legislators/legislators-current.json"
HISTORICAL_URL = "https://unitedstates.github.io/congress-legislators/legislators-historical.json"


def _load_env() -> None:
    for env_path in [
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return


def _norm(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    ).lower()


def _build_lookup(rows: list[dict], include_historical: bool) -> dict[tuple[str, str], str]:
    """Map (state, normalized_lastname) -> bioguide_id for senators."""
    lookup: dict[tuple[str, str], str] = {}
    collisions: list[tuple[tuple[str, str], str, str]] = []
    for L in rows:
        terms = L.get("terms") or []
        senate_terms = [t for t in terms if t.get("type") == "sen"]
        if not senate_terms:
            continue
        # For the historical pass we want the most recent senate term so that
        # if a person served in multiple states their last state wins.
        last = senate_terms[-1]
        state = last["state"]
        last_name = _norm(L["name"]["last"])
        bid = L["id"]["bioguide"]
        key = (state, last_name)
        if key in lookup and lookup[key] != bid:
            collisions.append((key, lookup[key], bid))
            # Keep the first match for current; in historical we don't care
            continue
        lookup[key] = bid
    return lookup


def _resolve_db_senator(
    official_id: str, state: str, full_name: str, current: dict, historical: dict
) -> str | None:
    """Return bioguide_id for this row, preferring current over historical."""
    parts = official_id.split("-")
    last_token = _norm(parts[0])
    last_word = _norm(full_name.split()[-1].rstrip(","))
    for source in (current, historical):
        for candidate in (last_token, last_word):
            bid = source.get((state, candidate))
            if bid:
                return bid
    return None


def main() -> int:
    _load_env()
    import psycopg2

    log.info("fetching legislators-current...")
    current_rows = httpx.get(CURRENT_URL, timeout=60, follow_redirects=True).json()
    log.info("fetching legislators-historical...")
    hist_rows = httpx.get(HISTORICAL_URL, timeout=60, follow_redirects=True).json()
    log.info("current=%d historical=%d", len(current_rows), len(hist_rows))

    current = _build_lookup(current_rows, include_historical=False)
    historical = _build_lookup(hist_rows, include_historical=True)

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute(
        "SELECT id, full_name, state, bioguide_id FROM officials "
        "WHERE chamber='senate' ORDER BY id"
    )
    rows = cur.fetchall()
    log.info("db senators (chamber=senate): %d", len(rows))

    updated = 0
    skipped_existing = 0
    unresolved: list[tuple[str, str, str]] = []
    for sid, full_name, state, existing_bid in rows:
        if existing_bid:
            skipped_existing += 1
            continue
        bid = _resolve_db_senator(sid, state, full_name, current, historical)
        if not bid:
            unresolved.append((sid, full_name, state))
            continue
        cur.execute(
            "UPDATE senators SET bioguide_id=%s, updated_at=NOW() WHERE id=%s",
            (bid, sid),
        )
        updated += 1

    conn.commit()
    cur.close()
    conn.close()

    log.info(
        "updated=%d  already_set=%d  unresolved=%d",
        updated,
        skipped_existing,
        len(unresolved),
    )
    for u in unresolved:
        log.warning("  unresolved: %s", u)
    return 0 if not unresolved else 1


if __name__ == "__main__":
    sys.exit(main())
