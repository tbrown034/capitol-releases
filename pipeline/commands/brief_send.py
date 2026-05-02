"""
Capitol Releases -- Daily Brief Email Sender

Fetches the latest published brief, renders HTML + text, and ships it to
every active subscriber via SMTP. Each send writes the brief id and
timestamp on the subscriber row so a re-run of the same date is a no-op.

Usage:
    python -m pipeline brief-send                 # latest published brief
    python -m pipeline brief-send --date 2026-04-30
    python -m pipeline brief-send --dry-run       # build messages, skip SMTP
    python -m pipeline brief-send --limit 5       # cap recipients (for staging)
"""

from __future__ import annotations

import argparse
import logging
import os
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import psycopg2
import psycopg2.extras

from pipeline.lib.brief_email import render_html, render_subject, render_text

_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.environ["DATABASE_URL"]
SITE_URL = os.environ.get("SITE_URL", "https://capitol-releases.com").rstrip("/")
FROM_NAME = os.environ.get("BRIEF_FROM_NAME", "Capitol Releases")
FROM_ADDR = os.environ.get("BRIEF_FROM_ADDR") or os.environ.get("SMTP_USER", "")

log = logging.getLogger("capitol.brief.send")


def fetch_brief(conn, brief_date: str | None, edition: str) -> dict | None:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if brief_date:
        cur.execute(
            """
            SELECT id::text, brief_date::text, edition, headline, dek, lede, sections,
                   signals, silent, quotes,
                   source_release_ids::text[] AS source_release_ids,
                   cited_release_ids::text[] AS cited_release_ids
            FROM briefs
            WHERE brief_date = %s::date AND status = 'published' AND edition = %s
            LIMIT 1
            """,
            (brief_date, edition),
        )
    else:
        cur.execute(
            """
            SELECT id::text, brief_date::text, edition, headline, dek, lede, sections,
                   signals, silent, quotes,
                   source_release_ids::text[] AS source_release_ids,
                   cited_release_ids::text[] AS cited_release_ids
            FROM briefs
            WHERE status = 'published' AND edition = %s
            ORDER BY brief_date DESC
            LIMIT 1
            """,
            (edition,),
        )
    row = cur.fetchone()
    cur.close()
    return dict(row) if row else None


def fetch_citations_map(conn, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT pr.id::text AS id, pr.title, pr.source_url,
               s.full_name AS senator_name, s.party, s.state
        FROM press_releases pr
        JOIN senators s ON s.id = pr.official_id
        WHERE pr.id = ANY(%s::uuid[])
        """,
        (ids,),
    )
    out: dict[str, dict] = {}
    for r in cur.fetchall():
        out[r["id"]] = dict(r)
    cur.close()
    return out


def fetch_subscribers(conn, brief_id: str, limit: int | None) -> list[dict]:
    """Active subscribers who haven't already received this brief."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sql = """
        SELECT id::text, email, unsubscribe_token::text
        FROM newsletter_subscribers
        WHERE status = 'active'
          AND (last_sent_brief_id IS NULL OR last_sent_brief_id <> %s::uuid)
        ORDER BY subscribed_at ASC
    """
    params: tuple = (brief_id,)
    if limit:
        sql += " LIMIT %s"
        params = (brief_id, limit)
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows


def smtp_connect():
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    pwd = os.environ.get("SMTP_PASS", "")
    if port == 465:
        s = smtplib.SMTP_SSL(host, port)
    else:
        s = smtplib.SMTP(host, port)
        s.starttls()
    if user and pwd:
        s.login(user, pwd)
    return s


def build_message(
    *,
    brief: dict,
    citations: dict[str, dict],
    subscriber: dict,
) -> MIMEMultipart:
    unsubscribe_url = f"{SITE_URL}/api/newsletter/unsubscribe?token={subscriber['unsubscribe_token']}"
    subject = render_subject(brief)
    html_body = render_html(
        brief,
        citations_by_id=citations,
        site_url=SITE_URL,
        unsubscribe_url=unsubscribe_url,
    )
    text_body = render_text(
        brief,
        citations_by_id=citations,
        site_url=SITE_URL,
        unsubscribe_url=unsubscribe_url,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{FROM_NAME} <{FROM_ADDR}>"
    msg["To"] = subscriber["email"]
    # RFC 8058 / 2369 one-click unsubscribe headers
    msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def main():
    p = argparse.ArgumentParser(description="Send the brief email (daily or weekly).")
    p.add_argument("--date", help="Brief date YYYY-MM-DD; default = latest published")
    p.add_argument("--edition", choices=["daily", "weekly"], default="daily",
                   help="Which edition to send (default daily)")
    p.add_argument("--dry-run", action="store_true", help="Render but don't send")
    p.add_argument("--limit", type=int, help="Cap recipients (staging)")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    conn = psycopg2.connect(DB_URL)
    try:
        brief = fetch_brief(conn, args.date, args.edition)
        if not brief:
            log.error("No published %s brief found for %s", args.edition, args.date or "latest")
            sys.exit(2)

        log.info("Brief %s [%s] — %s", brief["brief_date"], brief["edition"], brief["headline"])
        citations = fetch_citations_map(conn, brief["cited_release_ids"] or [])
        subs = fetch_subscribers(conn, brief["id"], args.limit)
        log.info("Recipients: %d", len(subs))

        if not subs:
            log.info("No active subscribers needing this brief. Done.")
            return

        if not FROM_ADDR:
            log.error("BRIEF_FROM_ADDR / SMTP_USER not set")
            sys.exit(3)

        if args.dry_run:
            sample = build_message(brief=brief, citations=citations, subscriber=subs[0])
            log.info("DRY RUN. Sample subject: %r", sample["Subject"])
            log.info("Total HTML length: %d chars", len(sample.as_string()))
            return

        sent = 0
        failed = 0
        smtp = smtp_connect()
        try:
            for sub in subs:
                msg = build_message(brief=brief, citations=citations, subscriber=sub)
                try:
                    smtp.sendmail(FROM_ADDR, [sub["email"]], msg.as_string())
                    cur = conn.cursor()
                    cur.execute(
                        """
                        UPDATE newsletter_subscribers
                        SET last_sent_brief_id = %s::uuid, last_sent_at = NOW()
                        WHERE id = %s::uuid
                        """,
                        (brief["id"], sub["id"]),
                    )
                    conn.commit()
                    cur.close()
                    sent += 1
                    # Light rate limit: most SMTP relays cap at ~10/sec.
                    if sent % 25 == 0:
                        time.sleep(1)
                except Exception as e:
                    failed += 1
                    log.error("Send failed for %s: %s", sub["email"], e)
        finally:
            try:
                smtp.quit()
            except Exception:
                pass

        log.info("Done. Sent %d, failed %d.", sent, failed)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
