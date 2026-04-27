"""
Capitol Releases — Daily Data Health Report

Generates a single source of truth at `docs/data_health.md` (and a JSON
sidecar) describing per-senator collection state. Designed to overwrite
itself every run — the goal is *current* truth, not an audit log.

Why this exists: hand-written audit docs in `docs/` and `pipeline/recon/`
go stale within days because the corpus updates daily. By the time you
trust them, they lie. This command produces what every prior audit was
trying to produce, but as a derived artifact instead of a written one.

Usage:
    python -m pipeline health-report                    # generate both files
    python -m pipeline health-report --skip-live        # DB-only (no senator-site fetches)
    python -m pipeline health-report --json /tmp/h.json # custom output paths
    python -m pipeline health-report --md /tmp/h.md
    python -m pipeline health-report --senators warren-elizabeth merkley-jeff
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import psycopg2
from bs4 import BeautifulSoup

from pipeline.lib.http import create_client, fetch_with_retry
from pipeline.backfill import extract_listing_items, extract_item_data, parse_date

_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.environ["DATABASE_URL"]
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MD = REPO_ROOT / "docs" / "data_health.md"
DEFAULT_JSON = REPO_ROOT / "docs" / "data_health.json"

CONTENT_TYPES = [
    "press_release", "statement", "op_ed", "blog", "letter",
    "floor_statement", "presidential_action", "other",
]

# Per-senator lag threshold before we count it as a flag. Senators
# routinely have 1–4 day publishing gaps; the alert noise above 5d is
# usually real signal.
LAG_FLAG_DAYS = 5

# Senators whose suspiciously-round record counts have been investigated
# and confirmed legitimate. Mirrors test_data_quality.py's verified_ok
# set; keep in sync. Adding a senator here means "we know about this,
# it's not a pagination cap."
ROUND_COUNT_WHITELIST = {"tillis-thom", "baldwin-tammy", "moran-jerry"}


def fetch_senators(conn, ids: list[str] | None) -> list[dict]:
    """Read active members from the DB but overlay the press_release_url
    and selectors from the seed file. The DB row's press_release_url can
    drift from the seed because seed edits don't auto-sync to the DB; the
    daily updater reads from the seed, so the seed is the source of truth
    for live-probe URLs."""
    cur = conn.cursor()
    where = "WHERE status = 'active' AND chamber IN ('senate', 'executive')"
    params: list = []
    if ids:
        where += " AND id = ANY(%s)"
        params.append(ids)
    cur.execute(
        f"SELECT id, full_name, party, state, press_release_url, "
        f"       collection_method, parser_family "
        f"FROM senators {where} "
        f"ORDER BY full_name",
        params,
    )
    cols = [d[0] for d in cur.description]
    out = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()

    # Overlay seed values (URL, selectors) so health probes match what the
    # daily updater actually uses.
    seed_path = Path(__file__).resolve().parents[1] / "seeds" / "senate.json"
    if seed_path.exists():
        seed = {s["senator_id"]: s for s in json.loads(seed_path.read_text())["members"]}
        for row in out:
            sd = seed.get(row["id"])
            if sd:
                if sd.get("press_release_url"):
                    row["press_release_url"] = sd["press_release_url"]
                row["selectors"] = sd.get("selectors") or {}
    return out


def db_per_senator(conn) -> dict[str, dict[str, Any]]:
    """One pass over press_releases, group by senator + content_type."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT senator_id,
               content_type,
               count(*)::int,
               max(published_at)::date,
               min(published_at)::date
        FROM press_releases
        WHERE deleted_at IS NULL
          AND content_type != 'photo_release'
          AND published_at >= '2025-01-01'
        GROUP BY senator_id, content_type
        """
    )
    by_sid: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "by_type": {}, "latest": None, "earliest": None}
    )
    for sid, ctype, n, mx, mn in cur.fetchall():
        s = by_sid[sid]
        s["total"] += n
        s["by_type"][ctype] = n
        if mx and (s["latest"] is None or mx > s["latest"]):
            s["latest"] = mx
        if mn and (s["earliest"] is None or mn < s["earliest"]):
            s["earliest"] = mn
    cur.close()
    return by_sid


def db_drought_per_type(conn, today: date) -> dict[str, dict[str, int]]:
    """Days since last record per (senator, content_type)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT senator_id,
               content_type,
               (CURRENT_DATE - max(published_at)::date)::int AS drought_days
        FROM press_releases
        WHERE deleted_at IS NULL
          AND content_type != 'photo_release'
        GROUP BY senator_id, content_type
        """
    )
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for sid, ctype, drought in cur.fetchall():
        out[sid][ctype] = drought
    cur.close()
    return out


def db_latest_run(conn) -> dict[str, Any]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, started_at, finished_at,
               COALESCE((stats->>'total_inserted')::int, 0),
               COALESCE((stats->>'total_updated')::int, 0),
               COALESCE((stats->>'total_errors')::int, 0),
               COALESCE((stats->>'senators_processed')::int, 0)
        FROM scrape_runs
        WHERE run_type = 'daily' AND finished_at IS NOT NULL
        ORDER BY finished_at DESC LIMIT 1
        """
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        return {}
    rid, started, finished, ins, upd, errs, processed = row
    return {
        "run_id": rid,
        "started_at": started.isoformat() if started else None,
        "finished_at": finished.isoformat() if finished else None,
        "duration_s": (finished - started).total_seconds() if started and finished else None,
        "total_inserted": ins,
        "total_updated": upd,
        "total_errors": errs,
        "senators_processed": processed,
    }


def db_corpus_totals(conn) -> dict[str, int]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT count(*)::int FROM press_releases
        WHERE deleted_at IS NULL AND content_type != 'photo_release'
        """
    )
    total = cur.fetchone()[0]
    cur.execute(
        """
        SELECT count(*)::int FROM press_releases
        WHERE deleted_at IS NOT NULL
        """
    )
    deleted = cur.fetchone()[0]
    cur.execute(
        """
        SELECT count(*)::int FROM press_releases
        WHERE deleted_at IS NULL
          AND content_type != 'photo_release'
          AND published_at IS NULL
        """
    )
    undated = cur.fetchone()[0]
    cur.execute(
        """
        SELECT count(DISTINCT senator_id)::int FROM press_releases
        WHERE deleted_at IS NULL
          AND content_type != 'photo_release'
          AND published_at >= NOW() - interval '7 days'
        """
    )
    active_7d = cur.fetchone()[0]
    cur.execute(
        """
        SELECT count(DISTINCT senator_id)::int FROM press_releases
        WHERE deleted_at IS NULL
          AND content_type != 'photo_release'
          AND published_at >= NOW() - interval '30 days'
        """
    )
    active_30d = cur.fetchone()[0]
    cur.close()
    return {
        "total": total,
        "deleted_tombstones": deleted,
        "undated": undated,
        "senators_active_7d": active_7d,
        "senators_active_30d": active_30d,
    }


async def live_probe_one(client, senator: dict) -> dict[str, Any]:
    url = senator.get("press_release_url") or ""
    selectors = senator.get("selectors") or {}
    out: dict[str, Any] = {"live_status": None, "live_latest": None, "live_items": 0}
    if not url:
        out["live_error"] = "no press_release_url"
        return out
    try:
        resp = await fetch_with_retry(client, url)
        out["live_status"] = resp.status_code
        if resp.status_code != 200:
            return out
        soup = BeautifulSoup(resp.text, "lxml")
        items = extract_listing_items(soup, selectors)
        out["live_items"] = len(items)
        latest = None
        for item in items:
            _, dtxt, _ = extract_item_data(item, url, {})
            if not dtxt:
                continue
            d = parse_date(dtxt)
            if not d:
                continue
            d_only = d.date() if hasattr(d, "date") else d
            if latest is None or d_only > latest:
                latest = d_only
        out["live_latest"] = latest.isoformat() if latest else None
    except Exception as e:
        out["live_error"] = f"{type(e).__name__}: {e}"
    return out


async def live_probe(senators: list[dict], concurrency: int = 6) -> dict[str, dict[str, Any]]:
    sem = asyncio.Semaphore(concurrency)
    results: dict[str, dict[str, Any]] = {}

    async def one(senator: dict):
        async with sem:
            results[senator["id"]] = await live_probe_one(client, senator)

    async with create_client() as client:
        await asyncio.gather(*(one(s) for s in senators))
    return results


def per_senator_flags(
    sid: str,
    senator: dict,
    db: dict[str, Any],
    drought: dict[str, int],
    live: dict[str, Any] | None,
    armstrong_excluded: bool,
) -> list[str]:
    flags: list[str] = []
    if armstrong_excluded:
        return flags  # Armstrong's zero-state is whitelisted
    if db["total"] == 0:
        flags.append("zero-records")
        return flags  # nothing else to say
    if live and live.get("live_status") and live["live_status"] != 200:
        flags.append(f"live-http-{live['live_status']}")
    if live and live.get("live_items") == 0 and live.get("live_status") == 200:
        flags.append("live-zero-items")
    if live and live.get("live_latest") and db["latest"]:
        try:
            live_d = date.fromisoformat(live["live_latest"])
            lag = (live_d - db["latest"]).days
            if lag > LAG_FLAG_DAYS:
                flags.append(f"lag-{lag}d")
        except ValueError:
            pass
    # Suspicious round-counts (potential pagination cap). Skip
    # already-investigated senators whose round count is legitimate.
    if (
        db["total"] in (100, 200, 250, 300, 500, 1000)
        and db["total"] > 0
        and sid not in ROUND_COUNT_WHITELIST
    ):
        flags.append(f"round-count-{db['total']}")
    # NB: a "single-type-press_release" flag was tried and dropped. The
    # classifier is designed to let the section URL win -- everything in a
    # senator's /press-releases/ section is press_release regardless of
    # title, even items titled "STATEMENT:" or "OP-ED:". For senators
    # whose entire site is one section, 100% press_release is correct
    # behavior, not a classifier miss. Multi-type breakdowns only emerge
    # when a senator maintains a distinct /op-eds/, /blog/, etc. section,
    # which is exactly what backfill_silos.py + classifier URL rules
    # already handle. Flagging single-type would generate noise on every
    # well-behaved senator with a single publishing surface.
    return flags


def render_md(report: dict[str, Any]) -> str:
    rows = report["senators"]
    aggregate = report["aggregate"]
    run = report["latest_run"]
    corpus = report["corpus"]

    lines = [
        f"# Data Health Report — {report['generated_at_iso'][:10]}",
        "",
        "Auto-generated by `python -m pipeline health-report`. **Overwrites itself every run.**",
        "Don't take this as a journal — it's a snapshot of current state. Last hand-edited audit lives at git history.",
        "",
        f"_Generated {report['generated_at_iso']} from {report['mode']}._",
        "",
        "## Corpus totals",
        "",
        f"- **{corpus['total']:,}** in-window records (deleted tombstones not counted)",
        f"- **{corpus['undated']:,}** records missing publication date",
        f"- **{corpus['deleted_tombstones']:,}** tombstones (source-deleted, archived)",
        f"- **{corpus['senators_active_7d']:,}** of 100 senators published something in the last 7 days",
        f"- **{corpus['senators_active_30d']:,}** of 100 senators published something in the last 30 days",
        "",
    ]

    if run:
        lines += [
            "## Latest daily run",
            "",
            f"- `{run['run_id']}`  finished {run['finished_at']} ({run['duration_s']:.1f}s)",
            f"- +{run['total_inserted']} new, ~{run.get('total_updated', 0)} updated, "
            f"{run['total_errors']} errors, {run['senators_processed']} senators processed",
            "",
        ]

    flag_counts: Counter[str] = Counter()
    for r in rows:
        for f in r["flags"]:
            # Bucket flags by prefix (lag-12d → lag, round-count-250 → round-count)
            bucket = f.split("-")[0] if "-" in f else f
            flag_counts[bucket] += 1
    if flag_counts:
        lines += [
            "## Flagged senators",
            "",
            *[f"- **{n}** with `{flag}` flag" for flag, n in flag_counts.most_common()],
            "",
        ]
    else:
        lines += ["## Flagged senators", "", "_None._", ""]

    # Aggregate health line counts
    lines += [
        "## Aggregate",
        "",
        f"- {aggregate['ok']} senators clean (no flags)",
        f"- {aggregate['flagged']} senators with at least one flag",
        f"- median in-window record count: {aggregate['median_total']}",
        f"- median lag (DB latest vs live latest): "
        + (f"{aggregate['median_lag_days']}d" if aggregate.get("median_lag_days") is not None else "n/a (skip-live)"),
        "",
        "## Per-senator detail",
        "",
        "| Senator | ST | Method | Records | PR · ST · OE · BL · LT · FS | Latest DB | Latest Live | Lag | Flags |",
        "|---|---|---|---:|---|---|---|---:|---|",
    ]
    for r in rows:
        bt = r["by_type"]
        mix = " · ".join(
            str(bt.get(t, 0))
            for t in ("press_release", "statement", "op_ed", "blog", "letter", "floor_statement")
        )
        lag_str = f"{r['lag_days']}d" if r.get("lag_days") is not None else "—"
        live_str = r.get("live_latest") or "—"
        flags_str = ", ".join(f"`{f}`" for f in r["flags"]) or "—"
        lines.append(
            f"| {r['id']} | {r['state']} | {r['collection_method'] or '—'} | {r['total']} | "
            f"{mix} | {r['latest'] or '—'} | {live_str} | {lag_str} | {flags_str} |"
        )

    lines += [
        "",
        "---",
        "",
        f"_To regenerate: `python -m pipeline health-report`. To skip live probes: `--skip-live`._",
    ]
    return "\n".join(lines) + "\n"


async def build_report(
    senator_ids: list[str] | None,
    skip_live: bool,
) -> dict[str, Any]:
    conn = psycopg2.connect(DB_URL)
    senators = fetch_senators(conn, senator_ids)
    db_data = db_per_senator(conn)
    drought = db_drought_per_type(conn, date.today())
    run = db_latest_run(conn)
    corpus = db_corpus_totals(conn)
    conn.close()

    live_data: dict[str, dict[str, Any]] = {}
    if not skip_live:
        live_data = await live_probe(senators)

    rows = []
    for s in senators:
        sid = s["id"]
        is_armstrong = sid == "armstrong-alan"
        db = db_data.get(sid, {"total": 0, "by_type": {}, "latest": None, "earliest": None})
        live = live_data.get(sid, {}) if not skip_live else None
        flags = per_senator_flags(sid, s, db, drought.get(sid, {}), live, is_armstrong)
        lag_days = None
        if live and live.get("live_latest") and db["latest"]:
            try:
                live_d = date.fromisoformat(live["live_latest"])
                lag_days = (live_d - db["latest"]).days
            except ValueError:
                pass
        rows.append({
            "id": sid,
            "full_name": s["full_name"],
            "state": s["state"],
            "party": s["party"],
            "collection_method": s["collection_method"],
            "parser_family": s["parser_family"],
            "total": db["total"],
            "by_type": db["by_type"],
            "earliest": db["earliest"].isoformat() if db["earliest"] else None,
            "latest": db["latest"].isoformat() if db["latest"] else None,
            "drought_days": drought.get(sid, {}),
            "live_status": (live or {}).get("live_status"),
            "live_items": (live or {}).get("live_items"),
            "live_latest": (live or {}).get("live_latest"),
            "live_error": (live or {}).get("live_error"),
            "lag_days": lag_days,
            "flags": flags,
        })

    rows.sort(key=lambda r: (-len(r["flags"]), r["id"]))

    totals = sorted(r["total"] for r in rows)
    median_total = totals[len(totals) // 2] if totals else 0
    lags = [r["lag_days"] for r in rows if r["lag_days"] is not None]
    median_lag = sorted(lags)[len(lags) // 2] if lags else None

    return {
        "generated_at_iso": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "skip-live (DB only)" if skip_live else "DB + live probe",
        "corpus": corpus,
        "latest_run": run,
        "senators": rows,
        "aggregate": {
            "ok": sum(1 for r in rows if not r["flags"]),
            "flagged": sum(1 for r in rows if r["flags"]),
            "median_total": median_total,
            "median_lag_days": median_lag,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-live", action="store_true",
                        help="Skip live-site probes (DB-only report)")
    parser.add_argument("--md", default=str(DEFAULT_MD), help="Output Markdown path")
    parser.add_argument("--json", default=str(DEFAULT_JSON), help="Output JSON path")
    parser.add_argument("--senators", nargs="*", help="Only audit these senator_ids")
    parser.add_argument("--quiet", action="store_true", help="Don't print summary to stdout")
    args = parser.parse_args()

    report = asyncio.run(build_report(args.senators, args.skip_live))
    md = render_md(report)

    md_path = Path(args.md)
    json_path = Path(args.json)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md)
    json_path.write_text(json.dumps(report, indent=2, default=str))

    if not args.quiet:
        agg = report["aggregate"]
        print(
            f"\nData Health Report written to {md_path} ({len(md)} chars) "
            f"and {json_path}.\n"
            f"  {agg['ok']} clean / {agg['flagged']} flagged / median lag "
            f"{agg.get('median_lag_days') or 'n/a'} days.\n"
        )


if __name__ == "__main__":
    main()
