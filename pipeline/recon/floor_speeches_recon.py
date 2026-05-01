"""
Two-week prototype: Senate floor speeches from the Congressional Record.

Probes the most recent ~2 weeks of session days. For each daily issue:
  1. Fetch the package-level MODS XML (one ~2.7MB file, no API key needed)
  2. Walk all <relatedItem type="constituent"> entries (one per granule)
  3. Keep SENATE granules; drop procedural noise via title + subGranuleClass blocklists
  4. For each kept granule, fetch the plain-text HTM rendition
  5. Split the text into per-speaker turns using the MODS-provided parsed
     speaker markers (e.g. "Mr. KENNEDY") and emit one row per (granule, speaker)
     when the turn has substantive length.

Outputs:
  pipeline/recon/floor_speeches_recon_results.json  full per-granule + per-speech rows
  pipeline/recon/floor_speeches_recon_report.md     human-readable summary + samples
"""
from __future__ import annotations

import json
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import httpx

log = logging.getLogger("floor_speeches.recon")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OUT_DIR = Path(__file__).parent
RESULTS_PATH = OUT_DIR / "floor_speeches_recon_results.json"
REPORT_PATH = OUT_DIR / "floor_speeches_recon_report.md"

MODS_URL = "https://www.govinfo.gov/metadata/pkg/CREC-{date}/mods.xml"
NS = {"m": "http://www.loc.gov/mods/v3", "x": "http://www.w3.org/1999/xlink"}

# Procedural granule titles to drop. Compared case-insensitively, exact match
# after stripping leading/trailing whitespace.
PROCEDURAL_TITLES: set[str] = {
    "senate",
    "prayer",
    "pledge of allegiance",
    "reservation of leader time",
    "morning business",
    "recognition of the majority leader",
    "recognition of the minority leader",
    "executive calendar",
    "executive calendar (executive session)",
    "legislative session",
    "unanimous consent request",
    "unanimous consent requests",
    "adjournment",
    "appointment",
    "appointments",
    "additional cosponsors",
    "additional statements",
    "submitted resolutions",
    "statements on introduced bills and joint resolutions",
    "introduction of bills and joint resolutions",
    "measures placed on the calendar",
    "measures read the first time",
    "measures discharged",
    "enrolled bill signed",
    "enrolled bills signed",
    "executive and other communications",
    "petitions and memorials",
    "reports of committees",
    "amendments submitted and proposed",
    "text of amendments",
    "authority for committees to meet",
    "privileges of the floor",
    "notices of hearings",
    "program",
    "orders for",
    "orders for monday",
    "orders for tuesday",
    "orders for wednesday",
    "orders for thursday",
    "orders for friday",
}

# subGranuleClass values that indicate non-speech content. Empirically
# verified against the Apr 14-29 2026 sample: each of these exclusively
# yielded recess-procedure, scheduling-order, cloture-motion, bill-reading
# procedure, or committee report-back boilerplate.
PROCEDURAL_SUBCLASSES: set[str] = {
    "DAILYDIGEST",
    "FRONTMATTER",
    "ADJOURNMENT",
    "LEADTIME",
    "PRAYER",
    "PLEDGE",
    "RECMAJ",
    "RECMIN",
    "MORNBUS",
    "PROGRAM",
    "ORDERFORADJ",
    "ORDERFORADJOURN",
    "EXEC",
    "LEGSESSION",
    "UCREQ",
    "UCREQS",
    "ADCS",  # additional cosponsors
    "ADST",  # additional statements
    "AMSUB",  # amendments submitted
    "TEXTOFAM",
    "RECCOM",
    "EXECOMM",
    "PETMEM",
    "SUBRES",
    "INTBILL",
    "INTBILLRES",
    "MEASCAL",
    "MEASREAD",
    "MEASDIS",
    "ENBILL",
    "AUTHCOM",
    "PRIVFLR",
    "NOTHEAR",
    # Added after Apr 14-29 sample showed these were 100% procedural:
    "SRECESS",
    "SCLOTURE",
    "SORDERFOR",
    "SORDER",
    "SMEASUREDCAL",
    "SEXECREPORT",
    # Amendment text and bill-introduction housekeeping. The Apr 22 sample
    # showed Senate routinely entering 600+ amendment-text granules per
    # heavy-amendment day; these have a tagged "submitting" senator but
    # the body is bill/amendment language, not speech.
    "SAMENDMENTTEXTIND",
    "SAMENDMENTTEXT",
    "SAMENDMENTSSUB",
    "SLEGISLATIVE",
    "SCONBUSINESS",
    "SMBUSINESS",
    "SMSGHOUSE",
    "SREFERRED",
    "SREADFIRST",
    "EXECUTIVECOMM",
    "SCOMMREPORT",
    "SINTROBILLS",
    "SSUBMISSION",
    "SCOSPONSORS",
    "SSTATEMENTS",  # the header form; substantive ones use SSTATEMENTSIND
    "SRESOLUTION",
    "SAUTHORITY",
    "SPRIVILEGES",
    "CALLTOORDER",
}

# Subclasses that are MOSTLY procedural (vote announcements, roll-call
# tallies) but occasionally contain substantive speeches. Drop only when
# the text shows the procedural fingerprint.
CONDITIONAL_SUBCLASSES: set[str] = {"SEXECSESSION", "SEXECCAL"}

# Patterns that mark a chunk as a roll-call announcement rather than a speech.
ROLLCALL_RE = re.compile(
    r"\b(yeas--\d+|rollcall vote no\.|the result was announced|necessarily absent: the senator)",
    re.IGNORECASE,
)

# Marker that signals the next paragraph is bill text being read into the
# record by the clerk, not the senator's own words.
CLERK_READ_RE = re.compile(
    r"(the (?:senior )?assistant (?:bill |legislative |executive )?clerk read as follows|the clerk will report the bill by title)",
    re.IGNORECASE,
)

# Minimum word count for a speaker turn to be emitted as a "speech".
# Single-speaker granules below this threshold are still emitted (they're
# whole substantive remarks); multi-speaker granules only emit turns that
# clear the bar (filtering out colloquy interjections like "I yield back").
MIN_SOLO_WORDS = 60
MIN_TURN_WORDS = 100

DATE_RANGE_END = date(2026, 4, 29)
DATE_RANGE_DAYS = 16  # covers ~2 weeks even with a recess in the middle


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
    # Recess days redirect to /error with a 200 HTML page. Detect by the
    # absence of the MODS root element.
    if not r.content.lstrip().startswith(b"<?xml") and b"<mods" not in r.content[:500]:
        return None
    return r.content


def parse_constituents(mods_xml: bytes) -> list[dict]:
    """Parse the package MODS, return one dict per granule with metadata."""
    root = ET.fromstring(mods_xml)
    out: list[dict] = []
    for ri in root.findall("m:relatedItem[@type='constituent']", NS):
        ext = ri.find("m:extension", NS)
        gclass = ext.findtext("m:granuleClass", default="", namespaces=NS) if ext is not None else ""
        subclass = ext.findtext("m:subGranuleClass", default="", namespaces=NS) if ext is not None else ""
        title = (ri.findtext("m:titleInfo/m:title", default="", namespaces=NS) or "").strip()
        granule_id = ri.get("ID", "").removeprefix("id-")
        # HTML URL — find relatedItem otherFormat with .htm
        html_url = ""
        for rel in ri.findall("m:relatedItem[@type='otherFormat']", NS):
            href = rel.get(f"{{{NS['x']}}}href", "")
            if href.endswith(".htm"):
                html_url = href
                break
        # Detail URL
        detail_url = ""
        for ident in ri.findall("m:identifier", NS):
            if ident.get("type") == "uri":
                detail_url = (ident.text or "").strip()
                break
        # Speakers
        speakers = []
        if ext is not None:
            for cm in ext.findall("m:congMember", NS):
                if cm.get("chamber") != "S":
                    continue  # House members appearing in Senate sections are skipped
                parsed = ""
                fnf = ""
                lnf = ""
                for nm in cm.findall("m:name", NS):
                    t = nm.get("type")
                    if t == "parsed":
                        parsed = (nm.text or "").strip()
                    elif t == "authority-fnf":
                        fnf = (nm.text or "").strip()
                    elif t == "authority-lnf":
                        lnf = (nm.text or "").strip()
                speakers.append({
                    "bioguide_id": cm.get("bioGuideId", ""),
                    "party": cm.get("party", ""),
                    "state": cm.get("state", ""),
                    "role": cm.get("role", ""),
                    "parsed_marker": parsed,
                    "name_first_last": fnf,
                    "name_last_first": lnf,
                })
        out.append({
            "granule_id": granule_id,
            "title": title,
            "granule_class": gclass,
            "sub_granule_class": subclass,
            "html_url": html_url,
            "detail_url": detail_url,
            "speakers": speakers,
        })
    return out


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
    """Remove bill text and clerk-read inserts from a senator's speech.

    When a senator says 'I ask unanimous consent that the Senate proceed to
    consider S. NNN' the clerk then reads the bill title and the full bill
    text gets folded into the granule. The bill-text run continues until the
    senator next speaks (which we don't see at this layer because that would
    be the next speaker turn). For solo-speaker granules we cut everything
    after the clerk-read marker.
    """
    m = CLERK_READ_RE.search(text)
    if not m:
        return text
    return text[: m.start()].strip()


def is_rollcall_announcement(text: str) -> bool:
    """Heuristic: the first ~600 chars of a vote-announcement speech are
    dominated by 'I announce that the Senator from X is necessarily absent.'
    or 'The result was announced--yeas NN, nays NN'."""
    head = text[:600]
    return bool(ROLLCALL_RE.search(head))


PRE_RE = re.compile(r"<pre>(.*?)</pre>", re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")


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
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'"))
    return body


def split_speakers(text: str, speakers: list[dict]) -> list[dict]:
    """Split the granule text into per-speaker turns.

    Marker form in CR text: two leading spaces, then "Mr. SURNAME." (or Mrs./Ms./Miss).
    We anchor only on markers that match a MODS-provided parsed name to avoid
    accidentally splitting on the PRESIDING OFFICER, etc.
    """
    if not speakers:
        return []

    # Build a regex of MODS-provided markers, escaped. Allow optional
    # " of <STATE>" suffix that CR sometimes emits even when MODS omits it.
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
    # Combined pattern: line-start (^ via MULTILINE), two spaces, marker,
    # optional " of <Word>", period.
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
        chunk = text[start:end].strip()
        # Collapse whitespace runs
        chunk = re.sub(r"\s+", " ", chunk)
        word_count = len(chunk.split())
        turns.append({
            "speaker_marker": marker,
            "bioguide_id": speaker["bioguide_id"],
            "party": speaker["party"],
            "state": speaker["state"],
            "name_first_last": speaker["name_first_last"],
            "word_count": word_count,
            "text": chunk,
        })
    return turns


def merge_consecutive_same_speaker(turns: list[dict]) -> list[dict]:
    """When the same senator speaks across multiple paragraphs they get
    multiple match hits. Combine consecutive turns by the same bioguide_id."""
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


def emit_speeches(granule: dict, turns: list[dict]) -> list[dict]:
    """Apply the per-row threshold rules and return rows ready for storage."""
    rows: list[dict] = []
    if not turns:
        return rows

    distinct_speakers = {t["bioguide_id"] for t in turns}
    is_solo = len(distinct_speakers) == 1
    threshold = MIN_SOLO_WORDS if is_solo else MIN_TURN_WORDS

    if is_solo:
        # Combine the entire granule into one row for the single speaker
        all_text = " ".join(t["text"] for t in turns)
        all_text = strip_clerk_inserts(all_text)
        all_words = len(all_text.split())
        if all_words < threshold:
            return rows
        # Conditional vote-announcement filter
        if granule["sub_granule_class"] in CONDITIONAL_SUBCLASSES and is_rollcall_announcement(all_text):
            return rows
        only = turns[0]
        rows.append({
            "granule_id": granule["granule_id"],
            "title": granule["title"],
            "sub_granule_class": granule["sub_granule_class"],
            "detail_url": granule["detail_url"],
            "html_url": granule["html_url"],
            "bioguide_id": only["bioguide_id"],
            "speaker_marker": only["speaker_marker"],
            "party": only["party"],
            "state": only["state"],
            "name_first_last": only["name_first_last"],
            "word_count": all_words,
            "is_solo": True,
            "turn_index": 0,
            "text": all_text,
        })
    else:
        for i, t in enumerate(turns):
            cleaned = strip_clerk_inserts(t["text"])
            wc = len(cleaned.split())
            if wc < threshold:
                continue
            if granule["sub_granule_class"] in CONDITIONAL_SUBCLASSES and is_rollcall_announcement(cleaned):
                continue
            rows.append({
                "granule_id": granule["granule_id"],
                "title": granule["title"],
                "sub_granule_class": granule["sub_granule_class"],
                "detail_url": granule["detail_url"],
                "html_url": granule["html_url"],
                "bioguide_id": t["bioguide_id"],
                "speaker_marker": t["speaker_marker"],
                "party": t["party"],
                "state": t["state"],
                "name_first_last": t["name_first_last"],
                "word_count": wc,
                "is_solo": False,
                "turn_index": i,
                "text": cleaned,
            })
    return rows


def session_dates(end: date, days: int) -> Iterable[date]:
    for i in range(days):
        yield end - timedelta(days=i)


def run() -> dict:
    days_data: list[dict] = []
    all_speeches: list[dict] = []
    all_dropped: list[dict] = []
    speaker_speech_counts: Counter[str] = Counter()
    by_subclass: Counter[str] = Counter()

    with httpx.Client(headers={"User-Agent": "capitol-releases-recon/1.0"}) as client:
        for d in session_dates(DATE_RANGE_END, DATE_RANGE_DAYS):
            log.info("=== %s (%s) ===", d.isoformat(), d.strftime("%a"))
            mods = fetch_package_mods(d, client)
            if mods is None:
                days_data.append({"date": d.isoformat(), "dow": d.strftime("%a"), "in_session": False})
                continue
            granules = parse_constituents(mods)
            senate = [g for g in granules if g["granule_class"] == "SENATE"]
            kept = []
            dropped = []
            for g in senate:
                proc, reason = is_procedural(g)
                if proc:
                    dropped.append({**{k: g[k] for k in ("granule_id", "title", "sub_granule_class")}, "reason": reason})
                else:
                    kept.append(g)
            log.info("  granules: %d senate / %d kept / %d dropped", len(senate), len(kept), len(dropped))

            day_speeches: list[dict] = []
            for g in kept:
                if not g["html_url"]:
                    continue
                text = fetch_text(g["html_url"], client)
                time.sleep(0.15)  # gentle on govinfo
                if not text:
                    continue
                turns = split_speakers(text, g["speakers"])
                turns = merge_consecutive_same_speaker(turns)
                rows = emit_speeches(g, turns)
                for r in rows:
                    r["date"] = d.isoformat()
                    speaker_speech_counts[r["bioguide_id"]] += 1
                    by_subclass[g["sub_granule_class"] or "(none)"] += 1
                    day_speeches.append(r)

            all_speeches.extend(day_speeches)
            all_dropped.extend([{**dd, "date": d.isoformat()} for dd in dropped])
            days_data.append({
                "date": d.isoformat(),
                "dow": d.strftime("%a"),
                "in_session": True,
                "senate_granules": len(senate),
                "kept_granules": len(kept),
                "dropped_granules": len(dropped),
                "emitted_speeches": len(day_speeches),
            })

    summary = {
        "date_range": {
            "start": (DATE_RANGE_END - timedelta(days=DATE_RANGE_DAYS - 1)).isoformat(),
            "end": DATE_RANGE_END.isoformat(),
            "days_probed": DATE_RANGE_DAYS,
            "session_days_found": sum(1 for d in days_data if d.get("in_session")),
        },
        "totals": {
            "total_senate_granules": sum(d.get("senate_granules", 0) for d in days_data),
            "kept_granules": sum(d.get("kept_granules", 0) for d in days_data),
            "dropped_granules": sum(d.get("dropped_granules", 0) for d in days_data),
            "emitted_speeches": len(all_speeches),
            "distinct_speakers": len(speaker_speech_counts),
        },
        "thresholds": {
            "MIN_SOLO_WORDS": MIN_SOLO_WORDS,
            "MIN_TURN_WORDS": MIN_TURN_WORDS,
        },
        "by_subclass_kept": dict(by_subclass.most_common()),
        "top_speakers": speaker_speech_counts.most_common(20),
        "days": days_data,
    }
    return {
        "summary": summary,
        "speeches": all_speeches,
        "dropped": all_dropped,
    }


def write_report(data: dict) -> None:
    s = data["summary"]
    speeches = data["speeches"]

    # Pick samples: 1 short tribute, 1 long policy speech, 1 multi-speaker debate excerpt
    speeches_sorted = sorted(speeches, key=lambda r: r["word_count"])
    samples = []
    if speeches_sorted:
        samples.append(("shortest kept", speeches_sorted[0]))
        samples.append(("median", speeches_sorted[len(speeches_sorted) // 2]))
        samples.append(("longest", speeches_sorted[-1]))
        # First multi-speaker example
        multi = next((r for r in speeches if not r["is_solo"]), None)
        if multi:
            samples.append(("multi-speaker turn", multi))

    lines: list[str] = []
    lines.append("# Senate Floor Speeches — 2-Week Recon")
    lines.append("")
    lines.append(f"Probed {s['date_range']['start']} through {s['date_range']['end']} "
                 f"({s['date_range']['days_probed']} calendar days, "
                 f"{s['date_range']['session_days_found']} session days).")
    lines.append("")
    lines.append("## Totals")
    for k, v in s["totals"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Day breakdown")
    lines.append("")
    lines.append("| date | dow | session | senate granules | kept | dropped | speeches emitted |")
    lines.append("|------|-----|---------|-----------------|------|---------|------------------|")
    for d in s["days"]:
        if not d.get("in_session"):
            lines.append(f"| {d['date']} | {d['dow']} | no | - | - | - | - |")
        else:
            lines.append(f"| {d['date']} | {d['dow']} | yes | {d['senate_granules']} | {d['kept_granules']} | {d['dropped_granules']} | {d['emitted_speeches']} |")
    lines.append("")
    lines.append("## Top speakers (by speech count)")
    lines.append("")
    for bid, cnt in s["top_speakers"]:
        # find a sample row for the name
        nm = next((r["name_first_last"] for r in speeches if r["bioguide_id"] == bid), bid)
        st = next((f"{r['state']}-{r['party']}" for r in speeches if r["bioguide_id"] == bid), "")
        lines.append(f"- {nm} ({st}, {bid}): {cnt}")
    lines.append("")
    lines.append("## subGranuleClass distribution (kept)")
    lines.append("")
    for k, v in s["by_subclass_kept"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Samples")
    lines.append("")
    for label, r in samples:
        lines.append(f"### {label}: {r['title']} ({r['name_first_last']}, {r['state']}-{r['party']})")
        lines.append("")
        lines.append(f"- granule: `{r['granule_id']}`  ")
        lines.append(f"- subClass: `{r['sub_granule_class']}`  ")
        lines.append(f"- words: {r['word_count']}  ")
        lines.append(f"- url: {r['detail_url']}")
        lines.append("")
        lines.append("> " + r["text"][:1200].replace("\n", " ") + ("..." if len(r["text"]) > 1200 else ""))
        lines.append("")
    REPORT_PATH.write_text("\n".join(lines))
    log.info("wrote %s", REPORT_PATH)


def main() -> int:
    data = run()
    RESULTS_PATH.write_text(json.dumps(data, indent=2))
    log.info("wrote %s (%d speeches)", RESULTS_PATH, len(data["speeches"]))
    write_report(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
