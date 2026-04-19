"""
Re-date existing records using Playwright (real browser, passes Akamai WAF)
by extracting article:published_time meta tags from each detail page.

Slower than the httpx version but works on senate.gov subdomains that
actively block raw HTTP bursts.

Usage:
    python -m pipeline.scripts.redate_from_meta_playwright \\
        --senators scott-rick blackburn-marsha tillis-thom johnson-ron
"""

import argparse
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from playwright.sync_api import sync_playwright

env_path = Path(__file__).resolve().parents[1] / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("redate-pw")

ISO_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)")


def parse_iso(raw: str):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        m = ISO_RE.match(raw.strip())
        if m:
            try:
                return datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
            except Exception:
                return None
    return None


def extract_published(page):
    """Return (datetime, source, confidence) from a loaded detail page."""
    # article:published_time meta
    for attr in [
        'meta[property="article:published_time"]',
        'meta[name="article:published_time"]',
        'meta[property="og:article:published_time"]',
        'meta[name="datePublished"]',
        'meta[name="datewritten"]',
    ]:
        try:
            el = page.query_selector(attr)
            if el:
                content = el.get_attribute("content")
                if content:
                    dt = parse_iso(content)
                    if dt:
                        return dt, "meta_tag", 0.95
        except Exception:
            continue
    # time[datetime] fallback
    try:
        el = page.query_selector("time[datetime]")
        if el:
            dt = parse_iso(el.get_attribute("datetime"))
            if dt:
                return dt, "time_element", 0.90
    except Exception:
        pass
    return None, None, None


def process_senator(browser, senator_id: str, conn, dry_run: bool, delay_ms: int):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, source_url, published_at, date_source, date_confidence
        FROM press_releases
        WHERE senator_id = %s
          AND deleted_at IS NULL
          AND published_at >= '2025-01-01'
          AND (
                date_source IS NULL
             OR date_source = 'url_path'
             OR date_confidence < 0.9
          )
        ORDER BY published_at
        """,
        (senator_id,),
    )
    rows = cur.fetchall()
    cur.close()

    if not rows:
        log.info("%s: no candidates", senator_id)
        return {"senator": senator_id, "candidates": 0, "updated": 0, "errors": 0, "unchanged": 0}

    log.info("%s: %d candidates", senator_id, len(rows))
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1400, "height": 900},
        locale="en-US",
    )
    page = context.new_page()

    # Warm up with the listing page so WAF sees a natural session
    cur = conn.cursor()
    cur.execute("SELECT press_release_url FROM senators WHERE id = %s", (senator_id,))
    pr_url = cur.fetchone()[0]
    cur.close()
    try:
        page.goto(pr_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
    except Exception as e:
        log.warning("%s warmup failed: %s", senator_id, e)

    stats = {
        "senator": senator_id, "candidates": len(rows),
        "updated": 0, "unchanged": 0, "errors": 0, "start": time.monotonic(),
    }

    update_cur = conn.cursor()
    for i, row in enumerate(rows, 1):
        rec_id, url, cur_date, cur_source, cur_conf = row
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if resp is None or resp.status != 200:
                stats["errors"] += 1
                if stats["errors"] <= 3:
                    log.warning("%s: HTTP %s for %s", senator_id,
                                resp.status if resp else "?", url)
                continue
            dt, source, conf = extract_published(page)
            if dt is None:
                stats["errors"] += 1
                continue

            new_date = dt.astimezone(timezone.utc)
            cur_date_utc = cur_date.astimezone(timezone.utc) if cur_date else None
            day_changed = cur_date_utc is None or cur_date_utc.date() != new_date.date()
            conf_upgrade = (cur_conf or 0) < conf

            if not day_changed and not conf_upgrade:
                stats["unchanged"] += 1
                continue

            if day_changed:
                stats["updated"] += 1

            if not dry_run:
                update_cur.execute(
                    """
                    UPDATE press_releases
                    SET published_at = %s,
                        date_source = %s,
                        date_confidence = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (new_date, source, conf, rec_id),
                )
                if i % 25 == 0:
                    conn.commit()
                    log.info("%s: committed through record %d/%d (updated=%d errors=%d)",
                             senator_id, i, len(rows), stats["updated"], stats["errors"])
        except Exception as e:
            stats["errors"] += 1
            if stats["errors"] <= 3:
                log.warning("%s exception: %s — %s", senator_id, url, e)

        page.wait_for_timeout(delay_ms)

    if not dry_run:
        conn.commit()
    update_cur.close()
    context.close()

    stats["elapsed"] = time.monotonic() - stats["start"]
    log.info(
        "%s done: candidates=%d updated=%d unchanged=%d errors=%d (%.1fs)",
        senator_id, stats["candidates"], stats["updated"],
        stats["unchanged"], stats["errors"], stats["elapsed"],
    )
    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--senators", nargs="+", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--delay-ms", type=int, default=400,
        help="Pause between detail-page loads (ms)",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False

    all_stats = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for sid in args.senators:
                all_stats.append(
                    process_senator(browser, sid, conn, args.dry_run, args.delay_ms)
                )
        finally:
            browser.close()
    conn.close()

    print("\n=== SUMMARY ===")
    print(f"{'senator':<22} {'cand':>5} {'updated':>8} {'unch':>5} {'err':>5}")
    for s in all_stats:
        print(
            f"{s['senator']:<22} {s['candidates']:>5} {s['updated']:>8} "
            f"{s['unchanged']:>5} {s['errors']:>5}"
        )


if __name__ == "__main__":
    main()
