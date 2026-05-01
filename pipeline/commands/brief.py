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
    cutoff = datetime.combine(brief_day - timedelta(days=threshold_days), time(0, 0), tzinfo=ET)
    cutoff_utc = cutoff.astimezone(timezone.utc)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT s.id, s.full_name AS senator, s.party, s.state,
               MAX(pr.published_at) AS last_release
        FROM senators s
        LEFT JOIN press_releases pr
          ON pr.senator_id = s.id AND pr.deleted_at IS NULL
        WHERE s.status = 'active' AND s.chamber = 'senate'
        GROUP BY s.id, s.full_name, s.party, s.state
        HAVING MAX(pr.published_at) IS NULL OR MAX(pr.published_at) < %s
        """,
        (cutoff_utc,),
    )
    rows = cur.fetchall()
    cur.close()
    today_dt = datetime.combine(brief_day, time(0, 0), tzinfo=ET).astimezone(timezone.utc)
    out = []
    for r in rows:
        last = r["last_release"]
        days = (today_dt - last).days if last else 999
        out.append({
            "senator": f"Sen. {r['senator']}, {r['party']}-{r['state']}",
            "days_quiet": days,
        })
    out.sort(key=lambda x: -x["days_quiet"])
    # Cap at 10 — model doesn't need 100 entries
    return out[:10]


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
        max_tokens=8000,
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
    for key in ("headline", "dek", "lede", "sections"):
        if key not in brief and key != "dek":
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


def cited_ids_from_brief(brief: dict) -> list[str]:
    seen: list[str] = []
    for sec in brief.get("sections") or []:
        for rid in sec.get("release_ids") or []:
            if rid not in seen:
                seen.append(rid)
    for sig in brief.get("signals") or []:
        for rid in sig.get("release_ids") or []:
            if rid not in seen:
                seen.append(rid)
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
) -> str:
    cur = conn.cursor()
    if publish:
        # Retract any prior published brief for this date so the unique
        # partial index doesn't reject the new row. Replaces in place;
        # the prior row stays in the table for audit (status='retracted').
        cur.execute(
            """
            UPDATE briefs
            SET status = 'retracted',
                retracted_at = NOW(),
                retracted_reason = 'replaced by regeneration'
            WHERE brief_date = %s AND edition = 'daily' AND status = 'published'
            """,
            (brief_day,),
        )
    cur.execute(
        """
        INSERT INTO briefs (
          brief_date, edition, status, model_version, prompt_hash,
          headline, dek, lede, sections, signals, silent, external_context,
          source_release_ids, cited_release_ids,
          input_tokens, output_tokens, cost_usd, published_at
        ) VALUES (%s, 'daily', %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::uuid[], %s::uuid[], %s, %s, %s, %s)
        RETURNING id
        """,
        (
            brief_day,
            "published" if publish else "draft",
            MODEL,
            prompt_hash,
            brief.get("headline"),
            brief.get("dek"),
            brief.get("lede"),
            json.dumps(brief.get("sections") or []),
            json.dumps(brief.get("signals") or []),
            json.dumps(brief.get("silent") or []),
            json.dumps(brief.get("external_context") or []),
            source_ids,
            cited_ids_from_brief(brief),
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
    parser = argparse.ArgumentParser(description="Generate daily Capitol Releases brief")
    parser.add_argument("--date", help="Brief date (ET) in YYYY-MM-DD; defaults to today ET")
    parser.add_argument("--dry-run", action="store_true", help="Build inputs, skip API + DB write")
    parser.add_argument("--publish", action="store_true", help="Mark new row as published, not draft")
    parser.add_argument("--print", action="store_true", help="Print the generated brief to stdout")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

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


if __name__ == "__main__":
    main()
