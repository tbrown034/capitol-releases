"""
Capitol Releases -- Daily AI Brief

Synthesizes the day's press releases into an Axios-style brief modeled on
Trevor Brown's Capitol Watch / Democracy Watch newsletters at Oklahoma Watch.

Pipeline:
  1. Pull today's in-window releases (status=active, deleted_at IS NULL).
  2. Compute volume baseline (8-week DOW average).
  3. Pull silent-senator list (no release in 14+ days).
  4. Load Senate calendar context (recess windows, scheduled votes).
  5. Send to Sonnet 4.6 with the voice system prompt + structured JSON schema.
  6. Validate every cited release_id is in the input set.
  7. Persist to briefs (status='draft' by default; --publish promotes).

Usage:
    python -m pipeline brief                      # generate draft for today (ET)
    python -m pipeline brief --date 2026-04-30
    python -m pipeline brief --publish            # promote draft to published
    python -m pipeline brief --dry-run            # show inputs, skip API call
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras

from pipeline.lib.brief_prompt import SYSTEM_PROMPT, build_user_prompt
from pipeline.lib.brief_weekly_prompt import (
    WEEKLY_SYSTEM_PROMPT,
    build_weekly_user_prompt,
)

_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.environ["DATABASE_URL"]
ET = ZoneInfo("America/New_York")

# Sonnet 4.6 pricing (per 1M tokens)
PRICE_INPUT = 3.0
PRICE_OUTPUT = 15.0

MODEL = "claude-sonnet-4-6"

log = logging.getLogger("capitol.brief")


def et_day_window(d: date) -> tuple[datetime, datetime]:
    """Return UTC datetimes covering the ET calendar day d."""
    start = datetime.combine(d, time(0, 0), tzinfo=ET).astimezone(timezone.utc)
    end = datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=ET).astimezone(timezone.utc)
    return start, end


def fetch_day_releases(conn, brief_day: date) -> list[dict]:
    start, end = et_day_window(brief_day)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT pr.id::text AS id,
               s.full_name AS senator,
               s.party,
               s.state,
               pr.title,
               pr.published_at,
               pr.source_url,
               pr.content_type,
               pr.body_text
        FROM press_releases pr
        JOIN senators s ON s.id = pr.senator_id
        WHERE pr.published_at >= %s
          AND pr.published_at < %s
          AND pr.deleted_at IS NULL
          AND s.status = 'active'
          AND s.chamber = 'senate'
          AND pr.content_type IN ('press_release', 'statement', 'floor_statement', 'op_ed')
        ORDER BY pr.published_at ASC
        """,
        (start, end),
    )
    rows = cur.fetchall()
    cur.close()
    # Truncate body for token budget
    out = []
    for r in rows:
        body = (r["body_text"] or "").strip()
        if len(body) > 3500:
            body = body[:3500] + "..."
        out.append({
            "id": r["id"],
            "senator": r["senator"],
            "party": r["party"],
            "state": r["state"],
            "title": r["title"],
            "published_at": r["published_at"].isoformat() if r["published_at"] else None,
            "source_url": r["source_url"],
            "content_type": r["content_type"],
            "body_text": body,
        })
    return out


def compute_volume_baseline(conn, brief_day: date) -> dict:
    """Same-day-of-week mean over the prior 8 weeks."""
    cur = conn.cursor()
    today_start, today_end = et_day_window(brief_day)
    cur.execute(
        """
        SELECT COUNT(*) FROM press_releases pr
        JOIN senators s ON s.id = pr.senator_id
        WHERE pr.published_at >= %s AND pr.published_at < %s
          AND pr.deleted_at IS NULL AND s.status = 'active' AND s.chamber = 'senate'
        """,
        (today_start, today_end),
    )
    today_count = cur.fetchone()[0]

    counts = []
    for w in range(1, 9):
        d = brief_day - timedelta(days=7 * w)
        s, e = et_day_window(d)
        cur.execute(
            """
            SELECT COUNT(*) FROM press_releases pr
            JOIN senators s ON s.id = pr.senator_id
            WHERE pr.published_at >= %s AND pr.published_at < %s
              AND pr.deleted_at IS NULL AND s.status = 'active' AND s.chamber = 'senate'
            """,
            (s, e),
        )
        counts.append(cur.fetchone()[0])
    cur.close()

    if not counts:
        return {"today_count": today_count, "dow_average": None, "pct_above_baseline": None}
    avg = sum(counts) / len(counts)
    pct = ((today_count - avg) / avg * 100) if avg > 0 else None
    return {
        "today_count": today_count,
        "dow_average": round(avg, 1),
        "pct_above_baseline": round(pct, 1) if pct is not None else None,
        "dow": brief_day.strftime("%A"),
    }


def fetch_silent_senators(conn, brief_day: date, threshold_days: int = 14) -> list[dict]:
    """Senators with no release published before brief_day in the prior threshold_days.

    Uses MAX(published_at) constrained to <= brief_day so backfilled briefs
    reflect that date's silence list, not today's.
    """
    brief_day_end_utc = datetime.combine(
        brief_day + timedelta(days=1), time(0, 0), tzinfo=ET
    ).astimezone(timezone.utc)
    cutoff_utc = datetime.combine(
        brief_day - timedelta(days=threshold_days), time(0, 0), tzinfo=ET
    ).astimezone(timezone.utc)

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT s.id, s.full_name AS senator, s.party, s.state,
               MAX(pr.published_at) FILTER (WHERE pr.published_at < %s) AS last_release
        FROM senators s
        LEFT JOIN press_releases pr
          ON pr.senator_id = s.id AND pr.deleted_at IS NULL
        WHERE s.status = 'active' AND s.chamber = 'senate'
        GROUP BY s.id, s.full_name, s.party, s.state
        HAVING MAX(pr.published_at) FILTER (WHERE pr.published_at < %s) IS NULL
            OR MAX(pr.published_at) FILTER (WHERE pr.published_at < %s) < %s
        """,
        (brief_day_end_utc, brief_day_end_utc, brief_day_end_utc, cutoff_utc),
    )
    rows = cur.fetchall()
    cur.close()
    out = []
    for r in rows:
        last = r["last_release"]
        days = (brief_day_end_utc - last).days if last else 999
        out.append({
            "senator": f"Sen. {r['senator']}, {r['party']}-{r['state']}",
            "days_quiet": days,
        })
    out.sort(key=lambda x: -x["days_quiet"])
    return out[:10]


def fetch_quiet_week_senators(conn, week_start: date, week_end: date) -> list[dict]:
    """Senators with zero releases in [week_start, week_end] (inclusive)."""
    s_utc = datetime.combine(week_start, time(0, 0), tzinfo=ET).astimezone(timezone.utc)
    e_utc = datetime.combine(week_end + timedelta(days=1), time(0, 0), tzinfo=ET).astimezone(timezone.utc)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT s.full_name AS senator, s.party, s.state,
               COUNT(pr.id) FILTER (
                 WHERE pr.published_at >= %s AND pr.published_at < %s AND pr.deleted_at IS NULL
               ) AS week_count
        FROM senators s
        LEFT JOIN press_releases pr ON pr.senator_id = s.id
        WHERE s.status = 'active' AND s.chamber = 'senate'
        GROUP BY s.id, s.full_name, s.party, s.state
        HAVING COUNT(pr.id) FILTER (
                 WHERE pr.published_at >= %s AND pr.published_at < %s AND pr.deleted_at IS NULL
               ) = 0
        ORDER BY s.full_name
        """,
        (s_utc, e_utc, s_utc, e_utc),
    )
    rows = cur.fetchall()
    cur.close()
    days_in_window = (week_end - week_start).days + 1
    return [
        {
            "senator": f"Sen. {r['senator']}, {r['party']}-{r['state']}",
            "days_quiet_in_window": days_in_window,
        }
        for r in rows
    ]


def fetch_week_briefs(conn, week_start: date, week_end: date) -> list[dict]:
    """Daily briefs (status='published') with brief_date in the window."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id::text, brief_date::text, headline, dek, lede,
               sections, signals, silent
        FROM briefs
        WHERE brief_date >= %s AND brief_date <= %s
          AND edition = 'daily' AND status = 'published'
        ORDER BY brief_date ASC
        """,
        (week_start, week_end),
    )
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows


def fetch_week_release_index(conn, week_start: date, week_end: date) -> list[dict]:
    s_utc = datetime.combine(week_start, time(0, 0), tzinfo=ET).astimezone(timezone.utc)
    e_utc = datetime.combine(week_end + timedelta(days=1), time(0, 0), tzinfo=ET).astimezone(timezone.utc)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT pr.id::text AS id, s.full_name AS senator, s.party, s.state,
               pr.title, pr.published_at, pr.content_type
        FROM press_releases pr
        JOIN senators s ON s.id = pr.senator_id
        WHERE pr.published_at >= %s AND pr.published_at < %s
          AND pr.deleted_at IS NULL
          AND s.status = 'active' AND s.chamber = 'senate'
          AND pr.content_type IN ('press_release', 'statement', 'floor_statement', 'op_ed')
        ORDER BY pr.published_at ASC
        """,
        (s_utc, e_utc),
    )
    out = []
    for r in cur.fetchall():
        out.append({
            "id": r["id"],
            "senator": r["senator"],
            "party": r["party"],
            "state": r["state"],
            "title": r["title"],
            "published_at": r["published_at"].isoformat() if r["published_at"] else None,
            "content_type": r["content_type"],
        })
    cur.close()
    return out


def compute_weekly_volume(conn, week_start: date, week_end: date) -> dict:
    """This week's count vs a 12-week rolling average, plus party split."""
    s_utc = datetime.combine(week_start, time(0, 0), tzinfo=ET).astimezone(timezone.utc)
    e_utc = datetime.combine(week_end + timedelta(days=1), time(0, 0), tzinfo=ET).astimezone(timezone.utc)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT s.party, COUNT(*) FROM press_releases pr
        JOIN senators s ON s.id = pr.senator_id
        WHERE pr.published_at >= %s AND pr.published_at < %s
          AND pr.deleted_at IS NULL AND s.status = 'active' AND s.chamber = 'senate'
        GROUP BY s.party
        """,
        (s_utc, e_utc),
    )
    by_party = {"D": 0, "R": 0, "I": 0}
    total = 0
    for party, c in cur.fetchall():
        by_party[party or ""] = c
        total += c

    counts = []
    for w in range(1, 13):
        ws = week_start - timedelta(days=7 * w)
        we = week_end - timedelta(days=7 * w)
        ws_utc = datetime.combine(ws, time(0, 0), tzinfo=ET).astimezone(timezone.utc)
        we_utc = datetime.combine(we + timedelta(days=1), time(0, 0), tzinfo=ET).astimezone(timezone.utc)
        cur.execute(
            """
            SELECT COUNT(*) FROM press_releases pr
            JOIN senators s ON s.id = pr.senator_id
            WHERE pr.published_at >= %s AND pr.published_at < %s
              AND pr.deleted_at IS NULL AND s.status = 'active' AND s.chamber = 'senate'
            """,
            (ws_utc, we_utc),
        )
        counts.append(cur.fetchone()[0])
    cur.close()

    avg = sum(counts) / len(counts) if counts else 0
    pct = ((total - avg) / avg * 100) if avg > 0 else None
    return {
        "this_week_count": total,
        "twelve_week_average": round(avg, 1),
        "pct_vs_baseline": round(pct, 1) if pct is not None else None,
        "by_party": by_party,
    }


def calendar_context_for(brief_day: date) -> dict:
    """Senate calendar context, sourced from senate.gov 2026 schedule JSON."""
    cal_path = Path(__file__).resolve().parent.parent / "seeds" / f"senate_calendar_{brief_day.year}.json"
    if not cal_path.exists():
        return {"is_recess": False, "recess_label": None, "scheduled_votes": []}

    cal = json.loads(cal_path.read_text())
    is_recess = False
    recess_label = None
    days_until_recess = None
    next_recess_label = None
    is_first_day_of_recess = False
    is_last_day_of_recess = False

    for r in cal.get("recesses", []):
        start = date.fromisoformat(r["start"])
        end = date.fromisoformat(r["end"])
        if start <= brief_day <= end:
            is_recess = True
            recess_label = r["label"]
            is_first_day_of_recess = brief_day == start
            is_last_day_of_recess = brief_day == end
            break
        if brief_day < start and (days_until_recess is None or (start - brief_day).days < days_until_recess):
            days_until_recess = (start - brief_day).days
            next_recess_label = r["label"]

    holiday = next((h["name"] for h in cal.get("holidays", []) if h["date"] == brief_day.isoformat()), None)

    try:
        from pipeline.lib.congress_votes import fetch_senate_votes_for_day
        votes = fetch_senate_votes_for_day(brief_day)
    except Exception as e:
        log.warning("Vote lookup raised: %s", e)
        votes = []

    return {
        "is_recess": is_recess,
        "recess_label": recess_label,
        "is_first_day_of_recess": is_first_day_of_recess,
        "is_last_day_of_recess": is_last_day_of_recess,
        "days_until_next_recess": days_until_recess,
        "next_recess_label": next_recess_label,
        "holiday": holiday,
        "scheduled_votes": votes,
    }


def call_claude(system: str, user: str) -> tuple[dict, dict]:
    """Send to Sonnet 4.6 via streaming, return (parsed_json, usage_dict).

    Streaming is required for this prompt: 35k+ input tokens plus a 4000-token
    structured output regularly exceeds the 60s non-streaming socket timeout.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, timeout=600.0)
    chunks: list[str] = []
    final_message = None
    with client.messages.stream(
        model=MODEL,
        max_tokens=12000,
        system=[
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user}],
    ) as stream:
        for text in stream.text_stream:
            chunks.append(text)
        final_message = stream.get_final_message()

    text = "".join(chunks).strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]

    # If the model hit max_tokens, the JSON will be truncated mid-string.
    # Surface a clear error with the stop_reason so we can bump the cap.
    stop_reason = getattr(final_message, "stop_reason", None)
    if stop_reason and stop_reason != "end_turn":
        raise RuntimeError(
            f"Model stopped on {stop_reason!r} (likely max_tokens hit). "
            f"Output was {len(text)} chars; bump max_tokens and retry."
        )
    parsed = json.loads(text)

    usage = {
        "input_tokens": final_message.usage.input_tokens,
        "output_tokens": final_message.usage.output_tokens,
        "cache_read_input_tokens": getattr(final_message.usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(final_message.usage, "cache_creation_input_tokens", 0) or 0,
    }
    return parsed, usage


def validate_brief(brief: dict, source_ids: set[str]) -> tuple[bool, list[str]]:
    """Reject any cited UUID not in the source set. Returns (ok, errors)."""
    errors: list[str] = []
    for key in ("headline", "lede", "sections"):
        if key not in brief:
            errors.append(f"missing required field: {key}")
    sections = brief.get("sections") or []
    if not isinstance(sections, list):
        errors.append("sections must be a list")
        return (False, errors)
    for i, sec in enumerate(sections):
        ids = sec.get("release_ids") or []
        for rid in ids:
            if rid not in source_ids:
                errors.append(f"section[{i}] cites unknown release_id: {rid}")
    return (len(errors) == 0, errors)


def validate_weekly(
    brief: dict, source_release_ids: set[str], source_brief_ids: set[str]
) -> tuple[bool, list[str]]:
    """Stricter validator for weekly. Every cited id must be in the source sets."""
    errors: list[str] = []
    for key in ("headline", "lede", "sections"):
        if key not in brief:
            errors.append(f"missing required field: {key}")

    def check_release_ids(label: str, ids):
        for rid in ids or []:
            if rid not in source_release_ids:
                errors.append(f"{label} cites unknown release_id: {rid}")

    def check_brief_ids(label: str, ids):
        for bid in ids or []:
            if bid not in source_brief_ids:
                errors.append(f"{label} cites unknown daily_brief_id: {bid}")

    check_release_ids("lede.lede_release_ids", brief.get("lede_release_ids"))
    check_brief_ids("lede.lede_brief_ids", brief.get("lede_brief_ids"))

    sections = brief.get("sections") or []
    if not isinstance(sections, list):
        errors.append("sections must be a list")
        return (False, errors)
    for i, sec in enumerate(sections):
        check_release_ids(f"section[{i}].release_ids", sec.get("release_ids"))
        check_brief_ids(f"section[{i}].brief_ids", sec.get("brief_ids"))

    for i, q in enumerate(brief.get("quotes") or []):
        rid = q.get("release_id")
        if rid and rid not in source_release_ids:
            errors.append(f"quotes[{i}] cites unknown release_id: {rid}")
        bid = q.get("daily_brief_id")
        if bid and bid not in source_brief_ids:
            errors.append(f"quotes[{i}] cites unknown daily_brief_id: {bid}")

    for i, d in enumerate(brief.get("drowned_out") or []):
        check_release_ids(f"drowned_out[{i}]", d.get("release_ids"))

    return (len(errors) == 0, errors)


def cited_ids_from_brief(brief: dict) -> list[str]:
    seen: list[str] = []

    def add(rid):
        if rid and rid not in seen:
            seen.append(rid)

    for sec in brief.get("sections") or []:
        for rid in sec.get("release_ids") or []:
            add(rid)
    for sig in brief.get("signals") or []:
        for rid in sig.get("release_ids") or []:
            add(rid)
    # Weekly fields
    for rid in brief.get("lede_release_ids") or []:
        add(rid)
    for q in brief.get("quotes") or []:
        add(q.get("release_id"))
    for d in brief.get("drowned_out") or []:
        for rid in d.get("release_ids") or []:
            add(rid)
    return seen


def estimate_cost(usage: dict) -> float:
    inp = usage["input_tokens"] / 1_000_000 * PRICE_INPUT
    out = usage["output_tokens"] / 1_000_000 * PRICE_OUTPUT
    cached = usage.get("cache_read_input_tokens", 0) / 1_000_000 * (PRICE_INPUT * 0.1)
    return round(inp + out + cached, 6)


def store_brief(
    conn,
    *,
    brief_day: date,
    brief: dict,
    source_ids: list[str],
    usage: dict,
    prompt_hash: str,
    publish: bool,
    edition: str = "daily",
) -> str:
    cur = conn.cursor()
    if publish:
        cur.execute(
            """
            UPDATE briefs
            SET status = 'retracted',
                retracted_at = NOW(),
                retracted_reason = 'replaced by regeneration'
            WHERE brief_date = %s AND edition = %s AND status = 'published'
            """,
            (brief_day, edition),
        )
    # Weekly briefs include quotes; daily briefs leave it null.
    cited = cited_ids_from_brief(brief)
    # For weekly, signals/silent are repurposed: silent <- quiet_weeks, signals <- volume callouts
    if edition == "weekly":
        signals_payload = []
        v = brief.get("volume") or {}
        if v:
            signals_payload.append({
                "kind": "volume",
                "note": (
                    f"Senate output: {v.get('this_week_count', 0)} releases this week vs. "
                    f"{v.get('twelve_week_average', 0)} 12-week average ({v.get('pct_vs_baseline', 0):+}%)."
                    if v.get("pct_vs_baseline") is not None else
                    f"Senate output: {v.get('this_week_count', 0)} releases this week."
                ),
            })
        for d in brief.get("drowned_out") or []:
            signals_payload.append({
                "kind": "drowned_out",
                "note": f"{d.get('headline', '')} — {d.get('body', '')}",
                "release_ids": d.get("release_ids") or [],
            })
        silent_payload = brief.get("quiet_weeks") or []
    else:
        signals_payload = brief.get("signals") or []
        silent_payload = brief.get("silent") or []

    cur.execute(
        """
        INSERT INTO briefs (
          brief_date, edition, status, model_version, prompt_hash,
          headline, dek, lede, sections, signals, silent, external_context,
          source_release_ids, cited_release_ids, quotes,
          input_tokens, output_tokens, cost_usd, published_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::uuid[], %s::uuid[], %s::jsonb, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            brief_day,
            edition,
            "published" if publish else "draft",
            MODEL,
            prompt_hash,
            brief.get("headline"),
            brief.get("dek"),
            brief.get("lede"),
            json.dumps(brief.get("sections") or []),
            json.dumps(signals_payload),
            json.dumps(silent_payload),
            json.dumps(brief.get("external_context") or []),
            source_ids,
            cited,
            json.dumps(brief.get("quotes")) if brief.get("quotes") else None,
            usage["input_tokens"],
            usage["output_tokens"],
            estimate_cost(usage),
            datetime.now(timezone.utc) if publish else None,
        ),
    )
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return str(new_id)


def main():
    parser = argparse.ArgumentParser(description="Generate daily or weekly Capitol Releases brief")
    parser.add_argument("--date", help="Daily brief date (ET) YYYY-MM-DD; defaults to today ET")
    parser.add_argument("--weekly", action="store_true", help="Generate weekly brief instead of daily")
    parser.add_argument(
        "--week-ending",
        help="Weekly: Thursday date the window ends on (ET) YYYY-MM-DD; defaults to most recent Thursday",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build inputs, skip API + DB write")
    parser.add_argument("--publish", action="store_true", help="Mark new row as published, not draft")
    parser.add_argument("--print", action="store_true", help="Print the generated brief to stdout")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.weekly:
        return run_weekly(args)

    if args.date:
        brief_day = date.fromisoformat(args.date)
    else:
        brief_day = datetime.now(ET).date()

    log.info("Building brief for %s (ET)", brief_day.isoformat())

    conn = psycopg2.connect(DB_URL)
    try:
        releases = fetch_day_releases(conn, brief_day)
        if not releases:
            log.warning("No releases for %s — refusing to generate empty brief", brief_day)
            sys.exit(2)

        baseline = compute_volume_baseline(conn, brief_day)
        silent = fetch_silent_senators(conn, brief_day)
        calendar = calendar_context_for(brief_day)

        log.info(
            "Inputs: %d releases, baseline %s, %d silent senators",
            len(releases), baseline.get("pct_above_baseline"), len(silent),
        )

        user_prompt = build_user_prompt(
            brief_date=brief_day.isoformat(),
            releases=releases,
            volume_baseline=baseline,
            calendar_context=calendar,
            silent_senators=silent,
            external_headlines=None,
        )
        prompt_hash = hashlib.sha256((SYSTEM_PROMPT + "\n---\n" + user_prompt).encode()).hexdigest()

        if args.dry_run:
            print(f"\n=== DRY RUN — brief for {brief_day} ===")
            print(f"  releases: {len(releases)}")
            print(f"  baseline: {baseline}")
            print(f"  silent (top 10): {silent[:5]}")
            print(f"  prompt hash: {prompt_hash[:12]}...")
            print(f"  user prompt size: {len(user_prompt):,} chars")
            return

        log.info("Calling Sonnet 4.6...")
        brief, usage = call_claude(SYSTEM_PROMPT, user_prompt)

        source_ids = [r["id"] for r in releases]
        ok, errors = validate_brief(brief, set(source_ids))
        if not ok:
            log.error("Validation failed:")
            for e in errors:
                log.error("  - %s", e)
            sys.exit(3)

        cost = estimate_cost(usage)
        log.info(
            "Generated brief. tokens in/out: %d/%d. est cost: $%.4f",
            usage["input_tokens"], usage["output_tokens"], cost,
        )

        new_id = store_brief(
            conn,
            brief_day=brief_day,
            brief=brief,
            source_ids=source_ids,
            usage=usage,
            prompt_hash=prompt_hash,
            publish=args.publish,
        )
        log.info("Stored brief %s (status=%s)", new_id, "published" if args.publish else "draft")

        if args.print:
            print(json.dumps(brief, indent=2))
    finally:
        conn.close()


def run_weekly(args):
    """Generate the weekly brief. Window: 7 days ending the chosen Thursday (Fri-Thu)."""
    if args.week_ending:
        week_end = date.fromisoformat(args.week_ending)
    else:
        # Most recent Thursday on or before today (ET).
        today = datetime.now(ET).date()
        # Python: Mon=0 ... Thu=3 ... Sun=6
        offset = (today.weekday() - 3) % 7
        week_end = today - timedelta(days=offset)

    if week_end.weekday() != 3:
        log.warning("--week-ending %s is not a Thursday; using anyway", week_end.isoformat())

    week_start = week_end - timedelta(days=6)  # Friday previous
    log.info("Building weekly brief: %s through %s", week_start.isoformat(), week_end.isoformat())

    conn = psycopg2.connect(DB_URL)
    try:
        daily_briefs = fetch_week_briefs(conn, week_start, week_end)
        if not daily_briefs:
            log.error("No published daily briefs in window; weekly needs them as input")
            sys.exit(2)

        release_index = fetch_week_release_index(conn, week_start, week_end)
        volume = compute_weekly_volume(conn, week_start, week_end)
        quiet = fetch_quiet_week_senators(conn, week_start, week_end)

        log.info(
            "Inputs: %d daily briefs, %d releases, %d quiet senators",
            len(daily_briefs), len(release_index), len(quiet),
        )

        user_prompt = build_weekly_user_prompt(
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
            daily_briefs=daily_briefs,
            release_index=release_index,
            volume=volume,
            quiet_senators=quiet,
        )
        prompt_hash = hashlib.sha256((WEEKLY_SYSTEM_PROMPT + "\n---\n" + user_prompt).encode()).hexdigest()

        if args.dry_run:
            print(f"\n=== DRY RUN — weekly {week_start} -> {week_end} ===")
            print(f"  daily_briefs: {len(daily_briefs)}")
            print(f"  release_index: {len(release_index)}")
            print(f"  volume: {volume}")
            print(f"  quiet (5+ days): {len(quiet)}")
            print(f"  prompt size: {len(user_prompt):,} chars")
            return

        log.info("Calling Sonnet 4.6 (weekly)...")
        brief, usage = call_claude(WEEKLY_SYSTEM_PROMPT, user_prompt)

        source_release_ids = [r["id"] for r in release_index]
        source_brief_ids = [b["id"] for b in daily_briefs]
        ok, errors = validate_weekly(brief, set(source_release_ids), set(source_brief_ids))
        if not ok:
            log.error("Validation failed:")
            for e in errors:
                log.error("  - %s", e)
            sys.exit(3)

        cost = estimate_cost(usage)
        log.info(
            "Generated weekly. tokens in/out: %d/%d. est cost: $%.4f",
            usage["input_tokens"], usage["output_tokens"], cost,
        )

        new_id = store_brief(
            conn,
            brief_day=week_end,
            brief=brief,
            source_ids=source_release_ids,
            usage=usage,
            prompt_hash=prompt_hash,
            publish=args.publish,
            edition="weekly",
        )
        log.info("Stored weekly brief %s (status=%s)", new_id, "published" if args.publish else "draft")
        if args.print:
            print(json.dumps(brief, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
