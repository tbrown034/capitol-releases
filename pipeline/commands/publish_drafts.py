"""Promote draft daily/weekly briefs to published.

Used to close the May 2-13 gap when the brief workflow defaulted to
draft. Going forward, the brief workflow passes --publish so cron output
is published directly.

Usage:
    python -m pipeline publish-drafts                     # all drafts (any date)
    python -m pipeline publish-drafts --since 2026-05-02  # drafts on/after a date
    python -m pipeline publish-drafts --dry-run           # show what would change

Behavior:
    - Only the most recent draft per (brief_date, edition) is promoted.
      Older drafts for the same day are retracted.
    - Any existing published row for the same (brief_date, edition) is
      retracted before promotion, matching the regenerate path.
"""

import argparse
import logging
import os
import sys
from datetime import date

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("publish-drafts")

DB_URL = os.environ["DATABASE_URL"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote draft briefs to published")
    parser.add_argument("--since", help="Only consider drafts with brief_date >= YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes, write nothing")
    args = parser.parse_args(sys.argv[1:])

    since = date.fromisoformat(args.since) if args.since else None

    conn = psycopg2.connect(DB_URL)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Pick the most recent draft per (brief_date, edition).
        cur.execute(
            """
            SELECT DISTINCT ON (brief_date, edition)
              id, brief_date, edition, generated_at
            FROM briefs
            WHERE status = 'draft'
              AND (%s::date IS NULL OR brief_date >= %s)
            ORDER BY brief_date, edition, generated_at DESC
            """,
            (since, since),
        )
        targets = cur.fetchall()
        if not targets:
            log.info("No draft briefs found%s.", f" since {since}" if since else "")
            return 0

        log.info("Found %d draft(s) to promote:", len(targets))
        for row in targets:
            log.info("  %s %s -> publish (id=%s)", row["brief_date"], row["edition"], row["id"])

        if args.dry_run:
            log.info("Dry run; nothing written.")
            return 0

        for row in targets:
            # Retract any existing published row for the same slot.
            cur.execute(
                """
                UPDATE briefs
                SET status = 'retracted',
                    retracted_at = NOW(),
                    retracted_reason = 'replaced by promoted draft'
                WHERE brief_date = %s AND edition = %s AND status = 'published'
                """,
                (row["brief_date"], row["edition"]),
            )
            # Retract older drafts in the same slot.
            cur.execute(
                """
                UPDATE briefs
                SET status = 'retracted',
                    retracted_at = NOW(),
                    retracted_reason = 'superseded by promoted draft'
                WHERE brief_date = %s AND edition = %s AND status = 'draft' AND id <> %s
                """,
                (row["brief_date"], row["edition"], row["id"]),
            )
            cur.execute(
                """
                UPDATE briefs
                SET status = 'published',
                    published_at = NOW()
                WHERE id = %s
                """,
                (row["id"],),
            )
        conn.commit()
        log.info("Promoted %d brief(s).", len(targets))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
