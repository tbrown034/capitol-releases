"""Daily pipeline digest email.

Replaces the noise channel of GH Actions failure emails with a single
end-of-day summary covering: how many records the day's collectors
captured (per chamber), which members went silent, the data-quality
warnings the test suite logged, and any hard failures up top.

Run from CI after the last daily collector + the test suite:

    python -m pipeline daily-report                # send for today (ET)
    python -m pipeline daily-report --date 2026-05-15
    python -m pipeline daily-report --dry-run      # print, do not send

Reads docs/data_quality_run.json (written by `pipeline test`) for the
warning/failure list. Pulls capture stats from scrape_runs and silent
members from official_site_items. SMTP is the same path brief-send
uses (Resend over SMTP_SSL on port 465, or STARTTLS otherwise).
"""

import argparse
import json
import logging
import os
import smtplib
import sys
import time
from datetime import date, datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("daily-report")

DB_URL = os.environ["DATABASE_URL"]
ET = ZoneInfo("America/New_York")
REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "data_quality_run.json"


def _et_day_bounds(target: date) -> tuple[datetime, datetime]:
    """Return (start, end) timestamptz bounds for the ET calendar day `target`.

    `started_at` and `scraped_at` are TIMESTAMPTZ; comparing against
    `target::date` would silently use the database session's UTC clock,
    so a 9pm-ET capture (01:00 UTC the next day) would be filed under
    tomorrow. Using explicit ET-anchored datetimes converted to UTC
    keeps the digest aligned with the human "today ET" claim.
    """
    start_et = datetime(target.year, target.month, target.day, 0, 0, tzinfo=ET)
    end_et = start_et + timedelta(days=1)
    return start_et.astimezone(timezone.utc), end_et.astimezone(timezone.utc)


def _aggregate_runs(cur, target: date) -> dict:
    """Sum capture stats across every daily scrape_runs row for the ET date.

    The cron fires four times a day; each run records its own stats blob.
    Summing gives the day's total, which is what an end-of-day reader
    actually wants to see.
    """
    start, end = _et_day_bounds(target)
    cur.execute(
        """
        SELECT stats
        FROM scrape_runs
        WHERE run_type = 'daily'
          AND finished_at IS NOT NULL
          AND started_at >= %s
          AND started_at <  %s
        """,
        (start, end),
    )
    rows = cur.fetchall()
    inserted = updated = skipped = errors = 0
    runs = 0
    for (stats,) in rows:
        if not stats:
            continue
        runs += 1
        # update.py records "total_*" keys; older runs may use the bare
        # form. Fall back to bare keys so historical dates still render.
        inserted += int(stats.get("total_inserted", stats.get("inserted", 0)) or 0)
        updated += int(stats.get("total_updated", stats.get("updated", 0)) or 0)
        skipped += int(stats.get("total_skipped", stats.get("skipped", 0)) or 0)
        errors += int(stats.get("total_errors", stats.get("errors", 0)) or 0)
    return {
        "runs": runs,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


def _per_chamber_today(cur, target: date) -> list[tuple[str, int]]:
    """How many new rows landed during the ET day, broken out by chamber.

    Uses scraped_at because published_at lags reality (members publish
    yesterday's news today, etc.) — capture activity is what we care
    about for "what did the pipeline do today."
    """
    start, end = _et_day_bounds(target)
    cur.execute(
        """
        SELECT COALESCE(o.chamber, o.branch, 'unknown') AS bucket, COUNT(*)::int
        FROM official_site_items i
        JOIN officials o ON o.id = i.official_id
        WHERE i.scraped_at >= %s
          AND i.scraped_at <  %s
          AND i.deleted_at IS NULL
        GROUP BY 1
        ORDER BY 2 DESC
        """,
        (start, end),
    )
    return [(c, n) for c, n in cur.fetchall()]


def _silent_members(cur, days: int = 14) -> list[tuple[str, str, str, int]]:
    """Active US Congress members with no captures in the last N days.

    Filters to chamber IN ('senate','house') and jurisdiction='us'. State
    legislators (TX biennial sessions etc.) and exec sources have legitimate
    multi-month silences and would pollute the daily Congress digest.
    Filters to >= 30 records over the last 90 days so we don't flag
    genuinely low-volume offices (Armstrong, recess weeks, etc.) — same
    threshold as alerts.check_anomalies. Returns (id, name, chamber, last_90).
    """
    cur.execute(
        """
        WITH historical AS (
            SELECT official_id,
                   COUNT(*) FILTER (WHERE scraped_at > NOW() - INTERVAL '90 days') AS last_90
            FROM official_site_items
            WHERE deleted_at IS NULL
            GROUP BY official_id
        ),
        recent AS (
            SELECT official_id, COUNT(*) AS cnt
            FROM official_site_items
            WHERE scraped_at > NOW() - (%s || ' days')::interval
              AND deleted_at IS NULL
            GROUP BY official_id
        )
        SELECT o.id, o.full_name, o.chamber, COALESCE(h.last_90, 0)
        FROM officials o
        JOIN historical h ON h.official_id = o.id
        LEFT JOIN recent r ON r.official_id = o.id
        WHERE h.last_90 >= 30
          AND COALESCE(r.cnt, 0) = 0
          AND o.status = 'active'
          AND o.chamber IN ('senate', 'house')
          AND o.jurisdiction = 'us'
        ORDER BY o.chamber, h.last_90 DESC
        LIMIT 25
        """,
        (str(days),),
    )
    return [(sid, name, chamber, last_90) for sid, name, chamber, last_90 in cur.fetchall()]


def _coverage_snapshot(cur) -> dict:
    """Top-line corpus state for context."""
    cur.execute("SELECT COUNT(*)::int FROM officials WHERE status = 'active'")
    members = cur.fetchone()[0]
    cur.execute(
        """
        SELECT COALESCE(chamber, branch, 'unknown'), COUNT(*)::int
        FROM officials
        WHERE status = 'active'
        GROUP BY 1
        ORDER BY 2 DESC
        """
    )
    by_chamber = list(cur.fetchall())
    cur.execute(
        "SELECT COUNT(*)::int FROM official_site_items WHERE deleted_at IS NULL"
    )
    total_items = cur.fetchone()[0]
    return {
        "members": members,
        "by_chamber": by_chamber,
        "total_items": total_items,
    }


def _read_quality_report() -> tuple[dict | None, str | None]:
    """Return (parsed_report, error_string). One of them is always None.

    error_string is set when the file is missing or unparseable so the
    digest can surface the failure loudly in the subject + body instead
    of silently presenting "0 warnings, 0 failures" — which would lie.
    """
    if not REPORT_PATH.exists():
        return None, f"missing ({REPORT_PATH.name} not written by `pipeline test`)"
    try:
        data = json.loads(REPORT_PATH.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return None, f"unreadable: {type(e).__name__}: {e}"
    # Tolerate older reports that may not have every key.
    if not isinstance(data, dict):
        return None, f"malformed: top-level was {type(data).__name__}, expected object"
    return data, None


def render(target: date) -> tuple[str, str]:
    """Build (subject, body) for the digest. Pure-ish — only DB reads."""
    conn = psycopg2.connect(DB_URL)
    try:
        cur = conn.cursor()
        runs = _aggregate_runs(cur, target)
        per_chamber = _per_chamber_today(cur, target)
        silent = _silent_members(cur)
        snapshot = _coverage_snapshot(cur)
    finally:
        conn.close()

    quality, quality_err = _read_quality_report()
    failures = (quality or {}).get("failures", []) if quality else []
    warnings = (quality or {}).get("warnings", []) if quality else []

    pretty_date = target.strftime("%A, %B %-d")
    new_total = runs["inserted"] + runs["updated"]
    fail_count = len(failures)
    warn_count = len(warnings)

    subject_bits = [f"Capitol Releases — {target.isoformat()}"]
    subject_bits.append(f"{new_total} captures")
    if quality_err:
        # Surface infrastructure problems loudly. A missing JSON usually
        # means the test step crashed in CI.
        subject_bits.append("REPORT MISSING")
    if fail_count:
        subject_bits.append(f"{fail_count} FAIL")
    if warn_count:
        subject_bits.append(f"{warn_count} warn")
    subject = " · ".join(subject_bits)

    lines: list[str] = []
    lines.append(f"Capitol Releases pipeline — {pretty_date}")
    lines.append("=" * 60)
    lines.append("")

    # Hard failures first. If any, this is the headline.
    if failures:
        lines.append(f"HARD FAILURES ({fail_count}) — pipeline considers data layer broken:")
        for f in failures:
            lines.append(f"  - {f['name']}: {f['message']}")
        lines.append("")

    lines.append("CAPTURES TODAY")
    lines.append("-" * 60)
    if runs["runs"] == 0:
        lines.append("  No daily runs recorded for this date.")
    else:
        lines.append(
            f"  {runs['runs']} cron run(s): {runs['inserted']} inserted, "
            f"{runs['updated']} updated, {runs['skipped']} skipped, "
            f"{runs['errors']} collector errors"
        )
    if per_chamber:
        lines.append("  By chamber:")
        for chamber, n in per_chamber:
            lines.append(f"    {chamber:<12} {n}")
    lines.append("")

    lines.append("CORPUS SNAPSHOT")
    lines.append("-" * 60)
    lines.append(f"  Active members: {snapshot['members']}")
    for chamber, n in snapshot["by_chamber"]:
        lines.append(f"    {chamber:<12} {n}")
    lines.append(f"  Total items (live): {snapshot['total_items']:,}")
    lines.append("")

    lines.append(f"WARNINGS ({warn_count})")
    lines.append("-" * 60)
    if warnings:
        for w in warnings:
            lines.append(f"  - {w['name']}")
            lines.append(f"      {w['message']}")
    else:
        lines.append("  None.")
    lines.append("")

    lines.append(f"SILENT MEMBERS — no captures in 14 days, normally active US Congress ({len(silent)})")
    lines.append("-" * 60)
    if silent:
        for sid, name, chamber, last_90 in silent:
            lines.append(f"  - [{chamber}] {name} ({sid}) — {last_90} records in last 90 days")
    else:
        lines.append("  None.")
    lines.append("")

    if quality_err:
        lines.append("REPORT INTEGRITY")
        lines.append("-" * 60)
        lines.append(f"  Data-quality report could NOT be loaded: {quality_err}")
        lines.append("  This usually means the `pipeline test` step crashed in CI;")
        lines.append("  check the daily-digest workflow logs. Counts above are still")
        lines.append("  accurate, but the warnings/failures section is empty by default.")
        lines.append("")

    return subject, "\n".join(lines)


def _send(subject: str, body: str) -> None:
    to_addr = os.environ.get("ALERT_EMAIL")
    smtp_host = os.environ.get("SMTP_HOST")
    if not to_addr or not smtp_host:
        log.warning("SMTP not configured (need ALERT_EMAIL + SMTP_HOST); printing instead.")
        print(body)
        return

    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    # Resend (and most providers) require From to be a verified domain
    # address, not the SMTP username. Prefer the same BRIEF_FROM_ADDR
    # secret brief-send.py uses; fall back to onboarding@resend.dev
    # (Resend's universal unverified sender — works for sends to a
    # verified account address) so this can ship before a domain is
    # verified on the Resend account. Swap by setting BRIEF_FROM_ADDR.
    from_addr = (
        os.environ.get("BRIEF_FROM_ADDR")
        or "onboarding@resend.dev"
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    def _attempt() -> None:
        # 30s socket timeout so a hung connection can't wedge the CI job for
        # the full 10-minute workflow budget without ever raising.
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as s:
                if smtp_user and smtp_pass:
                    s.login(smtp_user, smtp_pass)
                s.sendmail(from_addr, [to_addr], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
                s.starttls()
                if smtp_user and smtp_pass:
                    s.login(smtp_user, smtp_pass)
                s.sendmail(from_addr, [to_addr], msg.as_string())

    # This is the only operational alert channel, so a transient Resend or
    # network blip must not silently drop the digest. Retry with a short
    # backoff; re-raise on the final failure so CI goes red and the missing
    # email is itself a signal.
    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            _attempt()
            log.info("Sent daily report to %s", to_addr)
            return
        except (smtplib.SMTPException, OSError) as e:
            last_err = e
            log.warning("SMTP send attempt %d/3 failed: %s", attempt, e)
            if attempt < 3:
                time.sleep(5 * attempt)
    raise RuntimeError(f"daily-report SMTP send failed after 3 attempts: {last_err}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Send the pipeline daily digest")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (ET). Defaults to today ET.")
    parser.add_argument("--dry-run", action="store_true", help="Print only; do not send.")
    args = parser.parse_args(sys.argv[1:])

    target = (
        date.fromisoformat(args.date)
        if args.date
        else datetime.now(ET).date()
    )

    subject, body = render(target)
    if args.dry_run:
        print(f"Subject: {subject}")
        print()
        print(body)
        return 0
    _send(subject, body)
    return 0
