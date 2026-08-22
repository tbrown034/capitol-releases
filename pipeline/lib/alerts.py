"""
Alert system for Capitol Releases.

Stores alerts in the database and optionally sends email notifications.
Alerts are created by the updater, health checks, and anomaly detection.
"""

import json
import logging
import os
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.mime.text import MIMEText

import psycopg2

from pipeline.lib.cadence import stale_sources

log = logging.getLogger("capitol.alerts")


@dataclass
class Alert:
    """An alert to be stored and optionally delivered."""
    alert_type: str      # scrape_failure, selector_broken, cms_changed, deletion_detected, anomaly
    severity: str        # info, warning, error, critical
    message: str
    official_id: str = ""
    details: dict = field(default_factory=dict)


def store_alert(conn, alert: Alert):
    """Store an alert, collapsing repeats of a still-open condition.

    The updater runs 4x/day and re-derives the same anomalies every time, so a
    plain INSERT logged one row per condition per run: 31,296 rows accumulated
    between 2026-04-18 and 2026-07-25, of which ~2,900 per week were the same
    "last release was X" info alerts. Every alert consumer (the /admin
    dashboard, the API overview route, `pipeline review alerts`) reads
    ORDER BY created_at DESC LIMIT 10-50, so that backlog buried genuine
    error/critical alerts under stale-member noise.

    An unacknowledged alert with the same (alert_type, official_id, message) is
    the same open condition, not a new event. Touch the existing row instead of
    inserting: created_at moves to now so it still sorts as current, and
    details carries first_seen plus an occurrences counter so the history that
    matters is preserved. Acknowledging a row lets the condition alert again.
    """
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, details, created_at FROM alerts
            WHERE alert_type = %s
              AND official_id IS NOT DISTINCT FROM %s
              AND message = %s
              AND acknowledged = FALSE
            ORDER BY created_at DESC
            LIMIT 1
        """, (alert.alert_type, alert.official_id or None, alert.message))
        existing = cur.fetchone()

        if existing:
            alert_id, prev_details, first_created = existing
            details = dict(alert.details or {})
            prev = prev_details if isinstance(prev_details, dict) else {}
            details["first_seen"] = prev.get("first_seen") or first_created.isoformat()
            details["occurrences"] = int(prev.get("occurrences", 1)) + 1
            cur.execute("""
                UPDATE alerts
                SET created_at = NOW(), severity = %s, details = %s
                WHERE id = %s
            """, (alert.severity, json.dumps(details), alert_id))
        else:
            cur.execute("""
                INSERT INTO alerts (alert_type, official_id, severity, message, details)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                alert.alert_type,
                alert.official_id or None,
                alert.severity,
                alert.message,
                json.dumps(alert.details) if alert.details else None,
            ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error("Failed to store alert: %s", e)
    finally:
        cur.close()


def check_anomalies(conn) -> list[Alert]:
    """Check for per-senator anomalies after an update run.

    Detects:
    - Senators with 0 releases in last 7 days (normally active)
    - Sudden spikes in null fields
    - Senators whose last release is unusually old
    - Future-dated published_at (upstream typo on senator's site)
    """
    alerts = []
    cur = conn.cursor()

    # 1. Senators with 0 recent releases who normally post regularly.
    # A 14-day silence from a senator with >= 30 releases in the last
    # 90 days (~2.3/week cadence) is suspicious enough to check. Looser
    # thresholds produce false positives on legitimate quiet weeks
    # (recess, between PR drops).
    cur.execute("""
        WITH recent AS (
            SELECT official_id, COUNT(*) as cnt
            FROM official_site_items
            WHERE published_at > NOW() - INTERVAL '14 days'
              AND deleted_at IS NULL
            GROUP BY official_id
        ),
        historical AS (
            SELECT official_id, COUNT(*) as total,
                   COUNT(*) FILTER (WHERE published_at > NOW() - INTERVAL '90 days') as last_90,
                   COUNT(*) FILTER (WHERE published_at > NOW() - INTERVAL '30 days') as last_30
            FROM official_site_items
            WHERE deleted_at IS NULL
            GROUP BY official_id
            HAVING COUNT(*) > 20
        )
        SELECT h.official_id, h.total, h.last_90, COALESCE(r.cnt, 0) as recent_count
        FROM historical h
        LEFT JOIN recent r ON h.official_id = r.official_id
        WHERE COALESCE(r.cnt, 0) = 0
        AND h.last_90 >= 30
        AND h.last_30 >= 5
    """)
    for row in cur.fetchall():
        sid, total, last_90, recent = row
        alerts.append(Alert(
            alert_type="anomaly",
            severity="warning",
            message=f"{sid}: 0 releases in last 14 days but {last_90} in last 90 days. Possible collection issue.",
            official_id=sid,
            details={"total": total, "last_90": last_90, "last_7": recent},
        ))

    # 2. Senators with high null-date ratio in recent records
    cur.execute("""
        SELECT official_id,
               COUNT(*) as total,
               COUNT(*) FILTER (WHERE published_at IS NULL) as null_count
        FROM official_site_items
        WHERE scraped_at > NOW() - INTERVAL '3 days'
        GROUP BY official_id
        HAVING COUNT(*) > 3
        AND COUNT(*) FILTER (WHERE published_at IS NULL) > COUNT(*) * 0.5
    """)
    for row in cur.fetchall():
        sid, total, null_count = row
        alerts.append(Alert(
            alert_type="anomaly",
            severity="warning",
            message=f"{sid}: {null_count}/{total} recent records have null dates. Date parsing may be broken.",
            official_id=sid,
            details={"total_recent": total, "null_dates": null_count},
        ))

    # 3. Senators whose most recent release is older than expected
    # Tombstoned rows are excluded (deleted_at IS NULL) so a member whose
    # content was pulled from the source site reads as silent rather than
    # current. Former members are excluded too — they are permanently past
    # the 30-day threshold and alerting on them is noise that never clears.
    cur.execute("""
        SELECT s.id, s.full_name,
               MAX(pr.published_at) as last_release
        FROM officials s
        JOIN official_site_items pr ON s.id = pr.official_id
        WHERE s.collection_method IS NOT NULL
          AND s.status = 'active'
          AND pr.deleted_at IS NULL
        GROUP BY s.id, s.full_name
        HAVING MAX(pr.published_at) < NOW() - INTERVAL '30 days'
    """)
    for row in cur.fetchall():
        sid, name, last_release = row
        alerts.append(Alert(
            alert_type="anomaly",
            severity="info",
            message=f"{sid}: last release was {last_release.date()}. May need attention.",
            official_id=sid,
            details={"last_release": str(last_release.date())},
        ))

    # 4. Future-dated published_at — these are virtually always upstream
    # typos on the senator's senate.gov page (a date field set to a future
    # day by the press shop). We collect what they publish; flagging it
    # creates a paper trail without polluting email alerts (warning, not
    # error). Window of 1-60 days catches typos but excludes obvious parser
    # bugs (those go through test_dates_in_valid_range as failures).
    cur.execute("""
        SELECT official_id, source_url, published_at, scraped_at
        FROM official_site_items
        WHERE deleted_at IS NULL
          AND published_at > NOW() + INTERVAL '1 day'
          AND published_at <= NOW() + INTERVAL '60 days'
        ORDER BY scraped_at DESC
    """)
    for row in cur.fetchall():
        sid, source_url, pub_at, scraped_at = row
        alerts.append(Alert(
            alert_type="upstream_date_typo",
            severity="warning",
            message=(
                f"{sid}: source page lists published date as "
                f"{pub_at.strftime('%Y-%m-%d')} (future). Likely typo on "
                f"senator's senate.gov page."
            ),
            official_id=sid,
            details={
                "source_url": source_url,
                "published_at": str(pub_at),
                "scraped_at": str(scraped_at),
            },
        ))

    # 5. Sources quiet for longer than their own history predicts, with
    # peer comparison so an adjourned chamber does not read as breakage.
    # The fixed-threshold check above (#1) only sees sources publishing 30+
    # times a quarter, so it is blind to every part-time legislature.
    try:
        for profile in stale_sources(conn):
            alerts.append(Alert(
                alert_type="anomaly",
                severity="warning",
                message=profile.describe(),
                official_id=profile.official_id,
                details={
                    "days_since_last": round(profile.days_since_last, 1),
                    "threshold_days": round(profile.threshold_days, 1),
                    "p50_gap_days": round(profile.p50_days, 1),
                    "p95_gap_days": round(profile.p95_days, 1),
                    "cohort": profile.cohort,
                    "cohort_median_silence": round(profile.cohort_median_silence, 1),
                    "profiled": profile.profiled,
                },
            ))
    except psycopg2.Error as e:
        # A cadence failure must not take down the checks above it, which
        # cover breakage this one is explicitly not responsible for.
        log.warning("Cadence staleness check failed: %s", e)

    cur.close()
    return alerts


def check_ask_anomalies(conn) -> list[Alert]:
    """Watch the Ask-the-record notebook (ask_log) for trouble.

    The route logs every request but nothing read the table -- a broken
    guardrail (spiking validation failures, a probing IP, the daily cap
    burning out) was invisible until someone ran SQL by hand. Runs with
    the post-update anomaly checks; all thresholds are per rolling 24h.
    """
    alerts: list[Alert] = []
    failure_statuses = (
        "validation_failed", "protocol_error", "api_error",
        "retrieval_error", "refused",
    )
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT status, count(*) FROM ask_log
            WHERE created_at > NOW() - INTERVAL '24 hours'
            GROUP BY status
        """)
        counts = dict(cur.fetchall())
    except psycopg2.Error as e:
        # ask_log only exists where the Ask feature is deployed; its absence
        # must not take down the collector anomaly checks.
        conn.rollback()
        log.warning("Ask anomaly check skipped: %s", e)
        cur.close()
        return alerts

    total = sum(counts.values())
    failures = sum(counts.get(s, 0) for s in failure_statuses)

    # 1. Failure-rate spike: the answer path is broken or under attack.
    if failures >= 5 and failures > total * 0.3:
        alerts.append(Alert(
            alert_type="ask_failures",
            severity="error",
            message=(
                f"Ask: {failures}/{total} requests in 24h ended in a failure "
                f"status ({', '.join(s for s in failure_statuses if counts.get(s))})."
            ),
            details={"counts": counts},
        ))

    # 2. Daily cap reached: real demand or abuse, either way worth knowing.
    if total >= 250:
        alerts.append(Alert(
            alert_type="ask_cap_reached",
            severity="warning",
            message=f"Ask: global daily cap reached ({total} requests in 24h).",
            details={"counts": counts},
        ))

    # 3. One IP probing: many moderation declines or failures from a single
    # ip_hash reads as someone testing the guardrails.
    cur.execute("""
        SELECT ip_hash, count(*) FROM ask_log
        WHERE created_at > NOW() - INTERVAL '24 hours'
          AND status IN ('declined', 'validation_failed', 'protocol_error')
        GROUP BY ip_hash
        HAVING count(*) >= 10
    """)
    for ip_hash, n in cur.fetchall():
        alerts.append(Alert(
            alert_type="ask_probe",
            severity="warning",
            message=f"Ask: ip_hash {ip_hash[:12]}... hit {n} declined/failed requests in 24h.",
            details={"ip_hash": ip_hash, "count": n},
        ))

    cur.close()
    return alerts


def send_email_alerts(alerts: list[Alert]):
    """Send email notifications for error/critical alerts.

    Requires SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_EMAIL env vars.
    Silently skips if not configured.
    """
    alert_email = os.environ.get("ALERT_EMAIL")
    smtp_host = os.environ.get("SMTP_HOST")

    if not alert_email or not smtp_host:
        log.debug("Email alerts not configured, skipping")
        return

    critical = [a for a in alerts if a.severity in ("error", "critical")]
    if not critical:
        return

    body_lines = [f"Capitol Releases Pipeline: {len(critical)} alert(s)\n"]
    for a in critical:
        body_lines.append(f"[{a.severity.upper()}] {a.alert_type}")
        if a.official_id:
            body_lines.append(f"  Senator: {a.official_id}")
        body_lines.append(f"  {a.message}")
        body_lines.append("")

    msg = MIMEText("\n".join(body_lines))
    msg["Subject"] = f"Capitol Releases: {len(critical)} pipeline alert(s)"
    msg["From"] = os.environ.get("SMTP_USER", "alerts@capitol-releases.com")
    msg["To"] = alert_email

    try:
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")

        if smtp_port == 465:
            # SSL connection (Resend, etc.)
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(msg["From"], [alert_email], msg.as_string())
        else:
            # STARTTLS connection
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(msg["From"], [alert_email], msg.as_string())

        log.info("Sent %d alert emails to %s", len(critical), alert_email)
    except Exception as e:
        log.error("Failed to send alert email: %s", e)
