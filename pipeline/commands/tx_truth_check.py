"""TX live truth-check: hit each senate.texas.gov pressroom and compare
to the DB. Fails non-zero if any senator deviates by more than ±1 release.

Usage:
    python -m pipeline tx-truth

Why: TX is a separate corpus with its own publishing pattern. The federal
data-quality tests don't apply to it; this command is the analog. Run it
weekly or after any significant TX collector change to confirm we're
faithful to the source.
"""
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import psycopg2
from bs4 import BeautifulSoup


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
        FROM senators s
        WHERE s.chamber = 'tx_senate'
        ORDER BY (s.scrape_config->>'district')::int
        """
    )
    roster = cur.fetchall()

    cur.execute(
        """
        SELECT senator_id, count(*) AS n
        FROM press_releases pr
        JOIN senators s ON s.id = pr.senator_id
        WHERE s.chamber = 'tx_senate'
          AND pr.deleted_at IS NULL
          AND pr.content_type != 'photo_release'
          AND pr.published_at >= '2025-01-01'
        GROUP BY senator_id
        """
    )
    db_counts = dict(cur.fetchall())
    cur.close()
    conn.close()

    ua = "Mozilla/5.0 (compatible; CapitolReleases/1.0 truth-check)"
    client = httpx.Client(
        timeout=20.0,
        headers={"User-Agent": ua},
        follow_redirects=True,
    )

    print(f"{'Senator':<25} {'DB':>4} {'Live':>4} {'Δ':>5}  Status")
    print("-" * 60)

    deltas = []
    errors = []
    for sid, name, district, pr_url in roster:
        if not pr_url:
            pr_url = f"https://senate.texas.gov/pressroom.php?d={district}"
        db_n = db_counts.get(sid, 0)
        try:
            time.sleep(1.5)
            r = client.get(pr_url)
            if r.status_code != 200:
                errors.append((sid, name, f"HTTP {r.status_code}"))
                print(f"  {name[:24]:<24} {db_n:>4} {'?':>4} {'?':>5}  HTTP {r.status_code}")
                continue
            soup = BeautifulSoup(r.text, "lxml")
            text = soup.get_text("\n")
            in_window = 0
            for full, year in re.findall(r"(\d{1,2}/\d{1,2}/(\d{4}))", text):
                if year < "2025":
                    continue
                try:
                    if datetime.strptime(full, "%m/%d/%Y") >= datetime(2025, 1, 1):
                        in_window += 1
                except ValueError:
                    pass

            delta = in_window - db_n
            flag = "OK" if abs(delta) <= 1 else ("LOW" if delta > 1 else "HIGH")
            marker = "  " if abs(delta) <= 1 else "X "
            deltas.append((sid, name, db_n, in_window, delta))
            print(
                f"{marker}{name[:24]:<24} {db_n:>4} {in_window:>4} {delta:>+5}  {flag}"
            )
        except Exception as e:
            errors.append((sid, name, str(e)[:60]))
            print(f"  {name[:24]:<24} {db_n:>4} {'ERR':>4} {'?':>5}  {str(e)[:30]}")

    ok = [d for d in deltas if abs(d[4]) <= 1]
    bad = [d for d in deltas if abs(d[4]) > 1]
    print()
    print(f"Summary: {len(ok)}/{len(deltas)} senators within ±1 of live count")
    if errors:
        print(f"  Errors: {len(errors)}")
        for sid, name, err in errors:
            print(f"    {name}: {err}")
    if bad:
        print(f"  Deviations:")
        for sid, name, db_n, live, delta in bad:
            print(f"    {name}: DB={db_n} live={live} delta={delta:+d}")
        sys.exit(1)
    sys.exit(0 if not errors else 2)


if __name__ == "__main__":
    main()
