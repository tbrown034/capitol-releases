"""For each unverified silo from silo_probe_results.json, fetch the
section's listing page and count dated entries >= 2025-01-01.

The 19 senators with `needs_custom_scraper_unverified` silos serve sitemaps
without `<lastmod>` metadata, so we can't tell from the sitemap alone
whether a section is currently active. This verifier fetches the actual
listing page and parses dates from common patterns:

  1. <time datetime="...">  -- microformats / HTML5
  2. class="*date*" elements containing "Month DD, YYYY" text
  3. fallback: any "Month DD, YYYY" string in the page

Output: pipeline/recon/silo_verify_results.json keyed by senator with
each silo's first-page in-window count and the most-recent date seen.

Usage:
    python -m pipeline.scripts.silo_verify
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "pipeline" / "recon" / "silo_probe_results.json"
SEEDS = ROOT / "pipeline" / "seeds" / "senate.json"
OUT = ROOT / "pipeline" / "recon" / "silo_verify_results.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
DATE_TEXT_RE = re.compile(rf"({MONTHS})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})")
ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

MONTH_NUM = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def parse_dates(html: str) -> list[tuple[int, int, int]]:
    """Pull (year, month, day) tuples from the listing page.

    Tries <time datetime>, then visible "Month DD, YYYY" text, then
    ISO date strings. De-dupes within the page.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[tuple[int, int, int]] = []

    for t in soup.find_all("time"):
        dt = t.get("datetime") or t.get_text(strip=True)
        m = ISO_DATE_RE.search(dt)
        if m:
            try:
                out.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
                continue
            except ValueError:
                pass
        m = DATE_TEXT_RE.search(dt)
        if m:
            try:
                out.append(
                    (int(m.group(3)), MONTH_NUM[m.group(1).lower()], int(m.group(2)))
                )
            except (ValueError, KeyError):
                pass

    if not out:
        for el in soup.find_all(class_=re.compile(r"date", re.I)):
            txt = el.get_text(" ", strip=True)
            m = DATE_TEXT_RE.search(txt)
            if m:
                try:
                    out.append(
                        (int(m.group(3)), MONTH_NUM[m.group(1).lower()], int(m.group(2)))
                    )
                except (ValueError, KeyError):
                    pass

    if not out:
        for m in DATE_TEXT_RE.finditer(html):
            try:
                out.append(
                    (int(m.group(3)), MONTH_NUM[m.group(1).lower()], int(m.group(2)))
                )
            except (ValueError, KeyError):
                pass

    seen: set[tuple[int, int, int]] = set()
    deduped: list[tuple[int, int, int]] = []
    for d in out:
        if d not in seen:
            seen.add(d)
            deduped.append(d)
    return deduped


def in_window(d: tuple[int, int, int]) -> bool:
    return d >= (2025, 1, 1)


def find_post_links(html: str, section: str, base: str) -> list[str]:
    """Pull links from the listing page that point to children of `section`."""
    soup = BeautifulSoup(html, "lxml")
    sec_norm = section.rstrip("/")
    seen: set[str] = set()
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/"):
            href = base.rstrip("/") + href
        if not href.startswith(base):
            continue
        rel = href[len(base):]
        if not rel.startswith(sec_norm + "/"):
            continue
        tail = rel[len(sec_norm) + 1:]
        if not tail or "/" in tail.rstrip("/").split("/")[0] and len(tail.split("/")) > 2:
            continue
        if tail in ("page/", "page"):
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append(href)
    return out


def fetch_post_date(client: httpx.Client, url: str) -> tuple[int, int, int] | None:
    try:
        r = client.get(url, follow_redirects=True)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "lxml")
        for t in soup.find_all("time"):
            dt = t.get("datetime") or t.get_text(strip=True)
            m = ISO_DATE_RE.search(dt)
            if m:
                return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            m = DATE_TEXT_RE.search(dt)
            if m:
                try:
                    return (
                        int(m.group(3)),
                        MONTH_NUM[m.group(1).lower()],
                        int(m.group(2)),
                    )
                except (ValueError, KeyError):
                    pass
        for meta in soup.find_all("meta"):
            prop = (meta.get("property") or meta.get("name") or "").lower()
            if "publish" in prop or "date" in prop:
                content = meta.get("content") or ""
                m = ISO_DATE_RE.search(content)
                if m:
                    return (
                        int(m.group(1)),
                        int(m.group(2)),
                        int(m.group(3)),
                    )
        m = DATE_TEXT_RE.search(r.text)
        if m:
            try:
                return (
                    int(m.group(3)),
                    MONTH_NUM[m.group(1).lower()],
                    int(m.group(2)),
                )
            except (ValueError, KeyError):
                pass
    except Exception:
        return None
    return None


def verify_silo(client: httpx.Client, base: str, section: str) -> dict:
    url = f"{base.rstrip('/')}{section}"
    try:
        r = client.get(url, follow_redirects=True)
        if r.status_code != 200:
            return {"url": url, "status": r.status_code, "in_window_count": 0,
                    "most_recent": None, "page_size": 0,
                    "method": "listing-404"}
        dates = parse_dates(r.text)
        in_w = [d for d in dates if in_window(d)]
        most = max(dates) if dates else None
        method = "listing-dates"

        if len(in_w) == 0 and (not most or most < (2025, 1, 1)):
            post_links = find_post_links(r.text, section, base)[:5]
            sampled: list[tuple[int, int, int]] = []
            for plink in post_links:
                pd = fetch_post_date(client, plink)
                if pd:
                    sampled.append(pd)
            if sampled:
                in_w = [d for d in sampled if in_window(d)]
                most = max(sampled)
                method = f"sampled-{len(post_links)}-posts"

        return {
            "url": url,
            "status": 200,
            "in_window_count": len(in_w),
            "total_dates_found": len(dates),
            "most_recent": f"{most[0]:04d}-{most[1]:02d}-{most[2]:02d}" if most else None,
            "page_size": len(r.text),
            "method": method,
        }
    except Exception as e:
        return {"url": url, "status": 0, "error": str(e), "in_window_count": 0,
                "most_recent": None, "method": "error"}


def main() -> None:
    probe = json.loads(PROBE.read_text())
    seeds = {m["senator_id"]: m for m in json.loads(SEEDS.read_text())["members"]}

    targets: list[tuple[str, dict]] = []
    for sid, rows in probe.items():
        for r in rows:
            if r["classification"] in (
                "needs_custom_scraper",
                "needs_custom_scraper_unverified",
            ):
                targets.append((sid, r))

    print(f"verifying {len(targets)} silos...")
    out: dict[str, list[dict]] = {}

    headers = {"User-Agent": UA}
    with httpx.Client(timeout=20.0, headers=headers) as client:
        for sid, silo in targets:
            seed = seeds.get(sid)
            if not seed:
                continue
            base = (seed.get("official_url") or "").rstrip("/")
            verdict = verify_silo(client, base, silo["section"])
            in_w = verdict["in_window_count"]
            most = verdict.get("most_recent") or "-"
            method = verdict.get("method", "?")
            print(
                f"  {sid:25s} {silo['section']:40s} "
                f"in_window={in_w:>3} most_recent={most:10s} "
                f"sitemap={silo['count']:>5} via={method}"
            )
            out.setdefault(sid, []).append({**silo, **{"verify": verdict}})

    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT}")

    active = sum(1 for rows in out.values() for r in rows
                 if r["verify"]["in_window_count"] >= 5)
    sparse = sum(1 for rows in out.values() for r in rows
                 if 1 <= r["verify"]["in_window_count"] < 5)
    dormant = sum(1 for rows in out.values() for r in rows
                  if r["verify"]["in_window_count"] == 0)
    print(f"\nactive (>=5 in-window): {active}")
    print(f"sparse (1-4 in-window):  {sparse}")
    print(f"dormant (0 in-window):   {dormant}")


if __name__ == "__main__":
    main()
