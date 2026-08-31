"""
Capitol Releases -- Senate Floor Speeches Collector

Pulls Senate floor speeches from the Congressional Record (govinfo.gov)
and writes them to the floor_speeches table. One row per (granule,
speaker) where the speaker has substantive continuous text.

Usage:
    python -m pipeline floor-speeches update                      # since last run
    python -m pipeline floor-speeches update --days 3             # last 3 calendar days
    python -m pipeline floor-speeches backfill --since 2025-01-01 # explicit range
    python -m pipeline floor-speeches backfill --since 2025-01-01 --until 2025-06-30
    python -m pipeline floor-speeches --dry-run --days 1          # don't write to DB
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import httpx

log = logging.getLogger("capitol.floor_speeches")

NS = {"m": "http://www.loc.gov/mods/v3", "x": "http://www.w3.org/1999/xlink"}
MODS_URL = "https://www.govinfo.gov/metadata/pkg/CREC-{date}/mods.xml"

# Title-level procedural blocklist (case-insensitive exact match)
PROCEDURAL_TITLES: set[str] = {
    "senate", "prayer", "pledge of allegiance", "reservation of leader time",
    "morning business", "recognition of the majority leader",
    "recognition of the minority leader", "executive calendar",
    "executive calendar (executive session)", "legislative session",
    "unanimous consent request", "unanimous consent requests",
    "adjournment", "appointment", "appointments", "additional cosponsors",
    "additional statements", "submitted resolutions",
    "statements on introduced bills and joint resolutions",
    "introduction of bills and joint resolutions",
    "measures placed on the calendar", "measures read the first time",
    "measures discharged", "enrolled bill signed", "enrolled bills signed",
    "executive and other communications", "petitions and memorials",
    "reports of committees", "amendments submitted and proposed",
    "text of amendments", "authority for committees to meet",
    "privileges of the floor", "notices of hearings", "program",
    "orders for", "orders for monday", "orders for tuesday",
    "orders for wednesday", "orders for thursday", "orders for friday",
}

# subGranuleClass values that are 100% procedural in our 2-week sample.
PROCEDURAL_SUBCLASSES: set[str] = {
    "DAILYDIGEST", "FRONTMATTER", "ADJOURNMENT", "LEADTIME", "PRAYER",
    "PLEDGE", "RECMAJ", "RECMIN", "MORNBUS", "PROGRAM", "ORDERFORADJ",
    "ORDERFORADJOURN", "EXEC", "LEGSESSION", "UCREQ", "UCREQS",
    "ADCS", "ADST", "AMSUB", "TEXTOFAM", "RECCOM", "EXECOMM", "PETMEM",
    "SUBRES", "INTBILL", "INTBILLRES", "MEASCAL", "MEASREAD", "MEASDIS",
    "ENBILL", "AUTHCOM", "PRIVFLR", "NOTHEAR",
    "SRECESS", "SCLOTURE", "SORDERFOR", "SORDER", "SMEASUREDCAL",
    "SEXECREPORT",
    "SAMENDMENTTEXTIND", "SAMENDMENTTEXT", "SAMENDMENTSSUB",
    "SLEGISLATIVE", "SCONBUSINESS", "SMBUSINESS", "SMSGHOUSE",
    "SREFERRED", "SREADFIRST", "EXECUTIVECOMM", "SCOMMREPORT",
    "SINTROBILLS", "SSUBMISSION", "SCOSPONSORS", "SSTATEMENTS",
    "SRESOLUTION", "SAUTHORITY", "SPRIVILEGES", "CALLTOORDER",
    "VOTECHANGE", "SDISCHARGEREF",
}

# Vote-tally markers that signal the start of a rollcall printout
# concatenated onto the end of a senator's speech. Anything from these
# markers onward is page text, not the senator's words.
ROLLCALL_TALLY_RE = re.compile(
    r"(\[Rollcall Vote No\.|"
    r"yeas? and nays resulted--yeas|"
    r"yeas \d+, nays \d+, as follows:|"
    r"the result was announced--yeas)",
    re.IGNORECASE,
)

# Subclasses that mix substantive speeches with vote announcements; drop
# only when the text shows the rollcall fingerprint.
CONDITIONAL_SUBCLASSES: set[str] = {"SEXECSESSION", "SEXECCAL"}

ROLLCALL_RE = re.compile(
    r"\b(yeas--\d+|rollcall vote no\.|the result was announced|necessarily absent: the senator)",
    re.IGNORECASE,
)
CLERK_READ_RE = re.compile(
    r"(the (?:senior )?assistant (?:bill |legislative |executive )?clerk read as follows|the clerk will report the bill by title)",
    re.IGNORECASE,
)
PRE_RE = re.compile(r"<pre>(.*?)</pre>", re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")

# Solo-speaker granules below this length are dropped (filters out
# "Mr. President, I ask unanimous consent that..." procedural one-liners
# that slip past the title/subclass blocklist). Multi-speaker turns get a
# higher bar to filter colloquy interjections.
MIN_SOLO_WORDS = 60
MIN_TURN_WORDS = 100


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


# ---- MODS / HTM fetching ----------------------------------------------------

def fetch_package_mods(target: date, client: httpx.Client) -> bytes | None:
    url = MODS_URL.format(date=target.isoformat())
    try:
        r = client.get(url, timeout=60.0, follow_redirects=True)
    except Exception as e:
        log.warning("MODS fetch failed for %s: %s", target, e)
        return None
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        log.warning("MODS %s returned %s", target, r.status_code)
        return None
    if not r.content.lstrip().startswith(b"<?xml") and b"<mods" not in r.content[:500]:
        return None
    return r.content


def parse_constituents(mods_xml: bytes) -> list[dict]:
    root = ET.fromstring(mods_xml)
    out: list[dict] = []
    for ri in root.findall("m:relatedItem[@type='constituent']", NS):
        ext = ri.find("m:extension", NS)
        gclass = ext.findtext("m:granuleClass", default="", namespaces=NS) if ext is not None else ""
        subclass = ext.findtext("m:subGranuleClass", default="", namespaces=NS) if ext is not None else ""
        title = (ri.findtext("m:titleInfo/m:title", default="", namespaces=NS) or "").strip()
        granule_id = ri.get("ID", "").removeprefix("id-")
        congress_no = 0
        if ext is not None:
            try:
                # Use the first speaker's congress as the granule's congress
                cm = ext.find("m:congMember", NS)
                if cm is not None:
                    congress_no = int(cm.get("congress", "0") or 0)
            except (TypeError, ValueError):
                congress_no = 0
        html_url = ""
        for rel in ri.findall("m:relatedItem[@type='otherFormat']", NS):
            href = rel.get(f"{{{NS['x']}}}href", "")
            if href.endswith(".htm"):
                html_url = href
                break
        detail_url = ""
        for ident in ri.findall("m:identifier", NS):
            if ident.get("type") == "uri":
                detail_url = (ident.text or "").strip()
                break
        speakers = []
        if ext is not None:
            for cm in ext.findall("m:congMember", NS):
                if cm.get("chamber") != "S":
                    continue
                parsed = ""
                fnf = ""
                for nm in cm.findall("m:name", NS):
                    t = nm.get("type")
                    if t == "parsed":
                        parsed = (nm.text or "").strip()
                    elif t == "authority-fnf":
                        fnf = (nm.text or "").strip()
                speakers.append({
                    "bioguide_id": cm.get("bioGuideId", ""),
                    "party": cm.get("party", ""),
                    "state": cm.get("state", ""),
                    "parsed_marker": parsed,
                    "name_first_last": fnf,
                })
        out.append({
            "granule_id": granule_id,
            "title": title,
            "granule_class": gclass,
            "sub_granule_class": subclass,
            "html_url": html_url,
            "detail_url": detail_url,
            "speakers": speakers,
            "congress": congress_no,
        })
    return out


def fetch_text(url: str, client: httpx.Client) -> str | None:
    try:
        r = client.get(url, timeout=30.0, follow_redirects=True)
    except Exception as e:
        log.warning("HTM fetch failed for %s: %s", url, e)
        return None
    if r.status_code != 200:
        return None
    m = PRE_RE.search(r.text)
    if not m:
        return None
    body = m.group(1)
    body = HTML_TAG_RE.sub("", body)
    body = (body
            .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&#39;", "'"))
    return body


# ---- Filtering / parsing ----------------------------------------------------

def is_procedural(g: dict) -> tuple[bool, str]:
    title_norm = g["title"].strip().lower()
    if title_norm in PROCEDURAL_TITLES:
        return True, "procedural_title"
    if g["sub_granule_class"] in PROCEDURAL_SUBCLASSES:
        return True, f"procedural_subclass:{g['sub_granule_class']}"
    if not g["speakers"]:
        return True, "no_tagged_speaker"
    return False, ""


def strip_clerk_inserts(text: str) -> str:
    """Remove text that the page reads into the record after a senator yields:
    bill text following a 'clerk read as follows' cue, and rollcall vote
    tallies following a vote announcement. Both are page output, not
    speaker words, but they get concatenated into the speaker turn because
    no new speaker marker appears."""
    earliest = len(text)
    for rx in (CLERK_READ_RE, ROLLCALL_TALLY_RE):
        m = rx.search(text)
        if m and m.start() < earliest:
            earliest = m.start()
    if earliest == len(text):
        return text
    return text[:earliest].strip()


def is_rollcall_announcement(text: str) -> bool:
    return bool(ROLLCALL_RE.search(text[:600]))


def split_speakers(text: str, speakers: list[dict]) -> list[dict]:
    if not speakers:
        return []
    markers = []
    by_marker: dict[str, dict] = {}
    for s in speakers:
        m = s["parsed_marker"]
        if not m:
            continue
        markers.append(re.escape(m))
        by_marker[m] = s
    if not markers:
        return []
    pat = re.compile(
        r"^  (" + "|".join(markers) + r")(?: of [A-Z][a-z]+)?\.",
        re.MULTILINE,
    )
    matches = list(pat.finditer(text))
    if not matches:
        return []
    turns: list[dict] = []
    for i, m in enumerate(matches):
        marker = m.group(1)
        speaker = by_marker.get(marker)
        if not speaker:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = re.sub(r"\s+", " ", text[start:end].strip())
        turns.append({
            "speaker_marker": marker,
            "bioguide_id": speaker["bioguide_id"],
            "party": speaker["party"],
            "state": speaker["state"],
            "name_first_last": speaker["name_first_last"],
            "word_count": len(chunk.split()),
            "text": chunk,
        })
    return turns


def merge_consecutive_same_speaker(turns: list[dict]) -> list[dict]:
    if not turns:
        return turns
    merged = [turns[0].copy()]
    for t in turns[1:]:
        if t["bioguide_id"] == merged[-1]["bioguide_id"]:
            merged[-1]["text"] = merged[-1]["text"] + " " + t["text"]
            merged[-1]["word_count"] = len(merged[-1]["text"].split())
        else:
            merged.append(t.copy())
    return merged


def emit_speeches(granule: dict, turns: list[dict], speech_date: date) -> list[dict]:
    rows: list[dict] = []
    if not turns:
        return rows
    distinct = {t["bioguide_id"] for t in turns}
    is_solo = len(distinct) == 1
    threshold = MIN_SOLO_WORDS if is_solo else MIN_TURN_WORDS

    if is_solo:
        all_text = strip_clerk_inserts(" ".join(t["text"] for t in turns))
        wc = len(all_text.split())
        if wc < threshold:
            return rows
        if granule["sub_granule_class"] in CONDITIONAL_SUBCLASSES and is_rollcall_announcement(all_text):
            return rows
        only = turns[0]
        rows.append(_row(granule, only, all_text, wc, True, 0, speech_date))
    else:
        for i, t in enumerate(turns):
            cleaned = strip_clerk_inserts(t["text"])
            wc = len(cleaned.split())
            if wc < threshold:
                continue
            if granule["sub_granule_class"] in CONDITIONAL_SUBCLASSES and is_rollcall_announcement(cleaned):
                continue
            rows.append(_row(granule, t, cleaned, wc, False, i, speech_date))
    return rows


def _row(granule: dict, t: dict, text: str, wc: int, is_solo: bool, turn_index: int, speech_date: date) -> dict:
    return {
        "granule_id": granule["granule_id"],
        "bioguide_id": t["bioguide_id"],
        "turn_index": turn_index,
        "speech_date": speech_date,
        "title": granule["title"],
        "sub_granule_class": granule["sub_granule_class"] or None,
        "speaker_marker": t["speaker_marker"],
        "party": (t.get("party") or "")[:1] or None,
        "state": (t.get("state") or "")[:2] or None,
        "word_count": wc,
        "body_text": text,
        "is_solo": is_solo,
        "detail_url": granule["detail_url"],
        "html_url": granule["html_url"],
        "congress": granule["congress"] or 119,
    }


# ---- DB I/O -----------------------------------------------------------------

def get_last_speech_date(conn) -> date | None:
    cur = conn.cursor()
    cur.execute("SELECT MAX(speech_date) FROM floor_speeches")
    row = cur.fetchone()
    cur.close()
    return row[0] if row and row[0] else None


def get_official_id_by_bioguide(conn) -> dict[str, str]:
    cur = conn.cursor()
    cur.execute("SELECT bioguide_id, id FROM officials WHERE bioguide_id IS NOT NULL")
    out = {bid: sid for bid, sid in cur.fetchall()}
    cur.close()
    return out


def upsert_speeches(conn, rows: list[dict], scrape_run: str) -> tuple[int, int]:
    """Insert with ON CONFLICT DO NOTHING. Returns (inserted, skipped)."""
    if not rows:
        return 0, 0
    bioguide_to_senator = get_official_id_by_bioguide(conn)
    cur = conn.cursor()
    inserted = 0
    skipped = 0
    sql = """
    INSERT INTO floor_speeches
      (granule_id, bioguide_id, official_id, turn_index, speech_date, title,
       sub_granule_class, speaker_marker, party, state, word_count, body_text,
       is_solo, detail_url, html_url, congress, scrape_run)
    VALUES
      (%(granule_id)s, %(bioguide_id)s, %(official_id)s, %(turn_index)s, %(speech_date)s, %(title)s,
       %(sub_granule_class)s, %(speaker_marker)s, %(party)s, %(state)s, %(word_count)s, %(body_text)s,
       %(is_solo)s, %(detail_url)s, %(html_url)s, %(congress)s, %(scrape_run)s)
    ON CONFLICT (granule_id, bioguide_id, turn_index) DO NOTHING
    """
    for r in rows:
        r["official_id"] = bioguide_to_senator.get(r["bioguide_id"])
        r["scrape_run"] = scrape_run
        cur.execute(sql, r)
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1
    conn.commit()
    cur.close()
    return inserted, skipped


# ---- Driver -----------------------------------------------------------------

def collect_day(target: date, client: httpx.Client) -> list[dict]:
    mods = fetch_package_mods(target, client)
    if mods is None:
        return []
    granules = parse_constituents(mods)
    senate = [g for g in granules if g["granule_class"] == "SENATE"]
    rows: list[dict] = []
    fetched = 0
    for g in senate:
        proc, _reason = is_procedural(g)
        if proc:
            continue
        if not g["html_url"]:
            continue
        text = fetch_text(g["html_url"], client)
        fetched += 1
        time.sleep(0.15)
        if not text:
            continue
        turns = split_speakers(text, g["speakers"])
        turns = merge_consecutive_same_speaker(turns)
        rows.extend(emit_speeches(g, turns, target))
    log.info("  %s: %d senate granules, %d substantive fetches, %d speeches",
             target, len(senate), fetched, len(rows))
    return rows


def iter_dates(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="pipeline floor-speeches")
    sub = p.add_subparsers(dest="cmd")
    up = sub.add_parser("update", help="collect since last run (default)")
    up.add_argument("--days", type=int, default=None,
                    help="lookback window (overrides last-run inference)")
    bf = sub.add_parser("backfill", help="explicit date range")
    bf.add_argument("--since", required=True, help="start date YYYY-MM-DD")
    bf.add_argument("--until", default=None, help="end date YYYY-MM-DD (default today)")
    for s in (up, bf):
        s.add_argument("--dry-run", action="store_true",
                       help="don't write to DB; report counts only")
    args = p.parse_args(argv)
    if args.cmd is None:
        args.cmd = "update"
        args.days = None
        args.dry_run = False
    return args


def record_heartbeat(scrape_run: str, started_at: datetime, stats: dict) -> None:
    """Write a completion row to scrape_runs regardless of insert count.

    scraped_at on floor_speeches only advances when a run inserts rows, so
    a Senate recess is indistinguishable from a dead collector (the Aug 2026
    false alarm: 22 quiet days of pro-forma sessions tripped the 21-day
    freshness test). The heartbeat says "the collector ran and finished";
    test_floor_speeches_collector_alive reads it instead of scraped_at.
    """
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scrape_runs (id, run_type, started_at, finished_at, stats)
        VALUES (%s, 'floor_speeches', %s, NOW(), %s)
        ON CONFLICT (id) DO UPDATE SET finished_at = NOW(), stats = EXCLUDED.stats
        """,
        (scrape_run, started_at, json.dumps(stats)),
    )
    conn.commit()
    cur.close()
    conn.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _load_env()
    args = parse_args(sys.argv[1:])

    today = date.today()
    if args.cmd == "backfill":
        start = date.fromisoformat(args.since)
        end = date.fromisoformat(args.until) if args.until else today
    else:
        if args.days is not None:
            start = today - timedelta(days=args.days - 1)
            end = today
        else:
            import psycopg2
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            last = get_last_speech_date(conn)
            conn.close()
            if last is None:
                start = today - timedelta(days=2)
            else:
                # Re-fetch the last 2 days to catch late-publish issues
                start = last - timedelta(days=1)
            end = today

    log.info("range: %s -> %s", start, end)

    run_started = datetime.now(timezone.utc)
    scrape_run = f"floor-speeches-{run_started.strftime('%Y%m%d-%H%M%S')}"
    total_inserted = 0
    total_skipped = 0
    total_speeches = 0
    days_scanned = 0

    with httpx.Client(headers={"User-Agent": "capitol-releases/1.0 (floor_speeches)"}) as client:
        for d in iter_dates(start, end):
            days_scanned += 1
            rows = collect_day(d, client)
            total_speeches += len(rows)
            if not rows:
                continue
            if args.dry_run:
                continue
            import psycopg2
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            ins, skp = upsert_speeches(conn, rows, scrape_run)
            conn.close()
            total_inserted += ins
            total_skipped += skp

    if not args.dry_run:
        record_heartbeat(scrape_run, run_started, {
            "days_scanned": days_scanned,
            "speeches_found": total_speeches,
            "inserted": total_inserted,
            "skipped_dup": total_skipped,
            "range": [start.isoformat(), end.isoformat()],
        })

    log.info("DONE: %d speeches found, %d inserted, %d skipped (dup) %s",
             total_speeches, total_inserted, total_skipped,
             "[dry-run]" if args.dry_run else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
