"""TX live truth-check: hit each senate.texas.gov pressroom and compare
live source URLs to the DB. Fails non-zero if the DB is missing live URLs,
has extra live-window URLs, or has title/date drift for the same URL.

Usage:
    python -m pipeline tx-truth

Why: TX is a separate corpus with its own publishing pattern. The federal
data-quality tests don't apply to it; this command is the analog. Run it
weekly or after any significant TX collector change to confirm we're
faithful to the source.
"""
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg2
from bs4 import BeautifulSoup

from pipeline.collectors.tx_senate_collector import _extract_items
from pipeline.lib.identity import normalize_url


CUTOFF = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _load_env():
    """Load DATABASE_URL from .env or pipeline/.env if not already in env."""
    if "DATABASE_URL" in os.environ:
        return
    for p in [Path(".env"), Path("pipeline/.env")]:
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def main():
    _load_env()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.id, s.full_name,
               (s.scrape_config->>'district')::int AS district,
               s.press_release_url
        FROM officials s
        WHERE s.chamber = 'senate' AND s.jurisdiction = 'tx'
        ORDER BY (s.scrape_config->>'district')::int
        """
    )
    roster = cur.fetchall()

    cur.execute(
        """
        SELECT pr.official_id, pr.source_url, pr.title, pr.published_at
        FROM official_site_items pr
        JOIN officials s ON s.id = pr.official_id
        WHERE s.chamber = 'senate' AND s.jurisdiction = 'tx'
          AND pr.deleted_at IS NULL
          AND pr.content_type != 'photo_release'
          AND pr.published_at >= '2025-01-01'
        """
    )
    db_by_senator: dict[str, dict[str, dict]] = {}
    for sid, source_url, title, published_at in cur.fetchall():
        db_by_senator.setdefault(sid, {})[normalize_url(source_url)] = {
            "title": title or "",
            "published_at": published_at,
        }
    cur.close()
    conn.close()

    ua = "Mozilla/5.0 (compatible; CapitolReleases/1.0 truth-check)"
    client = httpx.Client(
        timeout=20.0,
        headers={"User-Agent": ua},
        follow_redirects=True,
    )

    print(f"{'Senator':<25} {'DB':>4} {'Live':>4} {'Miss':>4} {'Extra':>5} {'Drift':>5}  Status")
    print("-" * 78)

    summaries = []
    errors = []
    for sid, name, district, pr_url in roster:
        if not pr_url:
            pr_url = f"https://senate.texas.gov/pressroom.php?d={district}"
        db_rows = db_by_senator.get(sid, {})
        try:
            time.sleep(1.5)
            r = client.get(pr_url)
            if r.status_code != 200:
                errors.append((sid, name, f"HTTP {r.status_code}"))
                print(f"  {name[:24]:<24} {len(db_rows):>4} {'?':>4} {'?':>4} {'?':>5} {'?':>5}  HTTP {r.status_code}")
                continue
            soup = BeautifulSoup(r.text, "lxml")
            live_rows = {
                item["source_url"]: item
                for item in _extract_items(soup, pr_url)
                if item["published_at"] and item["published_at"] >= CUTOFF
            }

            db_urls = set(db_rows)
            live_urls = set(live_rows)
            missing = sorted(live_urls - db_urls)
            extra = sorted(db_urls - live_urls)
            drift = []
            for url in sorted(live_urls & db_urls):
                live = live_rows[url]
                db = db_rows[url]
                db_date = db["published_at"]
                if db_date and db_date.tzinfo is None:
                    db_date = db_date.replace(tzinfo=timezone.utc)
                date_drift = bool(
                    live["published_at"]
                    and db_date
                    and live["published_at"].date() != db_date.date()
                )
                title_drift = _norm_title(live["title"]) != _norm_title(db["title"])
                if date_drift or title_drift:
                    drift.append(url)

            ok = not missing and not extra and not drift
            flag = "OK" if ok else "DRIFT"
            marker = "  " if ok else "X "
            missing_info = [(url, live_rows[url]["published_at"], live_rows[url]["title"]) for url in missing]
            summaries.append((sid, name, len(db_rows), len(live_rows), missing_info, extra, drift))
            print(
                f"{marker}{name[:24]:<24} {len(db_rows):>4} {len(live_rows):>4} "
                f"{len(missing):>4} {len(extra):>5} {len(drift):>5}  {flag}"
            )
        except Exception as e:
            errors.append((sid, name, str(e)[:60]))
            print(f"  {name[:24]:<24} {len(db_rows):>4} {'ERR':>4} {'?':>4} {'?':>5} {'?':>5}  {str(e)[:30]}")

    ok = [s for s in summaries if not s[4] and not s[5] and not s[6]]
    bad = [s for s in summaries if s[4] or s[5] or s[6]]
    print()
    print(f"Summary: {len(ok)}/{len(summaries)} senators exactly match live URL set")
    if errors:
        print(f"  Errors: {len(errors)}")
        for sid, name, err in errors:
            print(f"    {name}: {err}")
    if bad:
        print("  Deviations:")
        for sid, name, db_n, live_n, missing_info, extra, drift in bad:
            print(
                f"    {name}: DB={db_n} live={live_n} "
                f"missing={len(missing_info)} extra={len(extra)} drift={len(drift)}"
            )
            for url, published_at, title in missing_info[:5]:
                print(f"      missing DB: {published_at} {title} {url}")
            for url in extra[:5]:
                print(f"      extra DB: {url}")
            for url in drift[:5]:
                print(f"      title/date drift: {url}")
        sys.exit(1)
    sys.exit(0 if not errors else 2)


def _norm_title(title: str) -> str:
    return " ".join((title or "").casefold().split())


if __name__ == "__main__":
    main()
