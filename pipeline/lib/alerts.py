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

log = logging.getLogger("capitol.alerts")


@dataclass
class Alert:
    """An alert to be stored and optionally delivered."""
    alert_type: str      # scrape_failure, selector_broken, cms_changed, deletion_detected, anomaly
    severity: str        # info, warning, error, critical
    message: str
    senator_id: str = ""
    details: dict = field(default_factory=dict)


def store_alert(conn, alert: Alert):
    """Store an alert in the database."""
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO alerts (alert_type, senator_id, severity, message, details)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            alert.alert_type,
            alert.senator_id or None,
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
            SELECT senator_id, COUNT(*) as cnt
            FROM press_releases
            WHERE published_at > NOW() - INTERVAL '14 days'
              AND deleted_at IS NULL
            GROUP BY senator_id
        ),
        historical AS (
            SELECT senator_id, COUNT(*) as total,
                   COUNT(*) FILTER (WHERE published_at > NOW() - INTERVAL '90 days') as last_90,
                   COUNT(*) FILTER (WHERE published_at > NOW() - INTERVAL '30 days') as last_30
            FROM press_releases
            WHERE deleted_at IS NULL
            GROUP BY senator_id
            HAVING COUNT(*) > 20
        )
        SELECT h.senator_id, h.total, h.last_90, COALESCE(r.cnt, 0) as recent_count
        FROM historical h
        LEFT JOIN recent r ON h.senator_id = r.senator_id
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
            senator_id=sid,
            details={"total": total, "last_90": last_90, "last_7": recent},
        ))

    # 2. Senators with high null-date ratio in recent records
    cur.execute("""
        SELECT senator_id,
               COUNT(*) as total,
               COUNT(*) FILTER (WHERE published_at IS NULL) as null_count
        FROM press_releases
        WHERE scraped_at > NOW() - INTERVAL '3 days'
        GROUP BY senator_id
        HAVING COUNT(*) > 3
        AND COUNT(*) FILTER (WHERE published_at IS NULL) > COUNT(*) * 0.5
    """)
    for row in cur.fetchall():
        sid, total, null_count = row
        alerts.append(Alert(
            alert_type="anomaly",
            severity="warning",
            message=f"{sid}: {null_count}/{total} recent records have null dates. Date parsing may be broken.",
            senator_id=sid,
            details={"total_recent": total, "null_dates": null_count},
        ))

    # 3. Senators whose most recent release is older than expected
    cur.execute("""
        SELECT s.id, s.full_name,
               MAX(pr.published_at) as last_release
        FROM senators s
        JOIN press_releases pr ON s.id = pr.senator_id
        WHERE s.collection_method IS NOT NULL
        GROUP BY s.id, s.full_name
        HAVING MAX(pr.published_at) < NOW() - INTERVAL '30 days'
    """)
    for row in cur.fetchall():
        sid, name, last_release = row
        alerts.append(Alert(
            alert_type="anomaly",
            severity="info",
            message=f"{sid}: last release was {last_release.date()}. May need attention.",
            senator_id=sid,
            details={"last_release": str(last_release.date())},
        ))

    # 4. Future-dated published_at — these are virtually always upstream
    # typos on the senator's senate.gov page (a date field set to a future
    # day by the press shop). We collect what they publish; flagging it
    # creates a paper trail without polluting email alerts (warning, not
    # error). Window of 1-60 days catches typos but excludes obvious parser
    # bugs (those go through test_dates_in_valid_range as failures).
    cur.execute("""
        SELECT senator_id, source_url, published_at, scraped_at
        FROM press_releases
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
            senator_id=sid,
            details={
                "source_url": source_url,
                "published_at": str(pub_at),
                "scraped_at": str(scraped_at),
            },
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
        if a.senator_id:
            body_lines.append(f"  Senator: {a.senator_id}")
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
