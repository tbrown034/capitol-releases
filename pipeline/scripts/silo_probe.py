"""Classify each surfaced silo from audit_sources as WP-JSON-ready or
needing a custom HTML scraper.

For each (senator, section_path) silo from docs/source_audit_report.md:

  1. Try GET {base}/wp-json/wp/v2/types via httpx then via Wayback.
  2. For every section subpath, try matching slugs against the post-type
     keys (e.g. "/news/op-eds/" -> try "op_eds", "op-eds", "opeds").
  3. For each match, GET {base}/wp-json/wp/v2/{slug}?per_page=1 to
     confirm a non-empty record set; record total from X-WP-Total.

Writes pipeline/recon/silo_probe_results.json:

  {senator_id: [
     {section, sitemap_count, classification, post_type_slug, wp_total}
  ]}

`classification` is one of:
  - "wp_extras_ready"     -- one EXTRAS line away from collection
  - "wp_already_collected"-- already in DB via existing collector
  - "needs_custom_scraper"-- not WP-JSON-accessible; needs HTML scraper
  - "low_value"           -- size below action threshold

Usage:
    python -m pipeline.scripts.silo_probe
    python -m pipeline.scripts.silo_probe --senator coons-chris
"""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
SEEDS = ROOT / "pipeline" / "seeds" / "senate.json"
REPORT = ROOT / "docs" / "source_audit_report.md"
OUT = ROOT / "pipeline" / "recon" / "silo_probe_results.json"

WAYBACK_TS = "2026"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

SILO_RE = re.compile(
    r"\|\s*([\d,]+)\s*\|\s*([A-Z]{2})\s*\|\s*([^|]+?)\s*\|\s*`(/[^`]+)`\s*\|"
)

LOW_VALUE_THRESHOLD = 20
WINDOW_PREFIX = "2025-"  # we also accept 2026-, see below
URL_LASTMOD_RE = re.compile(
    r"<url>\s*<loc>([^<]+)</loc>(?:\s*<lastmod>([^<]+)</lastmod>)?",
    re.DOTALL,
)


def parse_silos(report_path: Path) -> list[dict]:
    """Pull the 'Untapped silos' table out of the audit report."""
    text = report_path.read_text()
    silos: list[dict] = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("## Untapped silos"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        m = SILO_RE.match(line)
        if m:
            count_s, state, name, section = m.groups()
            silos.append(
                {
                    "count": int(count_s.replace(",", "")),
                    "state": state,
                    "senator_name": name.strip(),
                    "section": section.strip(),
                }
            )
    return silos


def slug_candidates(section: str) -> list[str]:
    """Generate candidate WP post-type slugs from a section path.

    e.g. "/news/op-eds/" -> ["op-eds", "op_eds", "opeds", "news"]
    e.g. "/newsroom/newsletters/" -> ["newsletters", "newsletter", "newsroom"]
    """
    parts = [p for p in section.strip("/").split("/") if p]
    cands: list[str] = []
    for p in reversed(parts):
        cands.append(p)
        if "-" in p:
            cands.append(p.replace("-", "_"))
            cands.append(p.replace("-", ""))
        if p.endswith("s"):
            cands.append(p[:-1])
            if "-" in p[:-1]:
                cands.append(p[:-1].replace("-", "_"))
    out: list[str] = []
    seen: set[str] = set()
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def fetch_text(client: httpx.Client, url: str) -> tuple[int, str, dict]:
    try:
        r = client.get(url, follow_redirects=True)
        return r.status_code, r.text, dict(r.headers)
    except Exception:
        return 0, "", {}


def fetch_via_wayback(client: httpx.Client, url: str) -> tuple[int, str, dict]:
    wb = f"https://web.archive.org/web/{WAYBACK_TS}id_/{url}"
    return fetch_text(client, wb)


def fetch_sitemap_lastmods(
    client: httpx.Client, base: str, depth: int = 0
) -> list[tuple[str, str]]:
    """Walk all sitemaps for `base`; return [(url, lastmod), ...].

    Tries httpx then Wayback. Caps recursion at depth 3.
    """
    if depth > 3:
        return []
    candidates = [
        f"{base}/sitemap_index.xml",
        f"{base}/wp-sitemap.xml",
        f"{base}/sitemap.xml",
    ]
    text = ""
    src = ""
    for url in candidates:
        for fetch in (fetch_text, fetch_via_wayback):
            status, t, _ = fetch(client, url)
            if status == 200 and ("<urlset" in t or "<sitemapindex" in t):
                text = t
                src = url
                break
        if text:
            break
    if not text:
        return []
    return _parse_sitemap_recursive(client, text, depth)


def _parse_sitemap_recursive(
    client: httpx.Client, text: str, depth: int
) -> list[tuple[str, str]]:
    if "<sitemapindex" in text:
        out: list[tuple[str, str]] = []
        children = re.findall(r"<loc>([^<]+\.xml[^<]*)</loc>", text)
        for child in children[:50]:
            for fetch in (fetch_text, fetch_via_wayback):
                status, t, _ = fetch(client, child)
                if status == 200 and "<urlset" in t:
                    out.extend(_parse_sitemap_recursive(client, t, depth + 1))
                    break
        return out
    pairs: list[tuple[str, str]] = []
    for m in URL_LASTMOD_RE.finditer(text):
        loc = m.group(1).strip()
        lastmod = (m.group(2) or "").strip()
        pairs.append((loc, lastmod))
    return pairs


def section_of(url: str) -> str | None:
    from urllib.parse import urlparse
    p = urlparse(url)
    parts = [x for x in p.path.split("/") if x]
    if len(parts) < 2:
        return f"/{parts[0]}/" if parts else None
    return f"/{parts[0]}/{parts[1]}/"


URL_YEAR_RE = re.compile(r"/(2025|2026)(?:/|-|$)")


def is_in_window(url: str, lastmod: str) -> bool:
    if lastmod and lastmod[:4] in ("2025", "2026"):
        return True
    if URL_YEAR_RE.search(url):
        return True
    return False


def in_window_counts_by_section(
    pairs: list[tuple[str, str]],
) -> tuple[dict[str, int], dict[str, str]]:
    """Count in-window URLs per section.

    Returns (counts_by_section, signal_by_section) where signal is one of:
      - "lastmod"  -> at least one lastmod >= 2025
      - "url-year" -> no lastmod but URL substring matches /2025|2026/
      - "none"     -> no signal -> count is 0 but value is unknown
    """
    counts: dict[str, int] = {}
    signal: dict[str, str] = {}
    section_has_any_lastmod: dict[str, bool] = {}
    for url, lastmod in pairs:
        sec = section_of(url)
        if not sec:
            continue
        if lastmod:
            section_has_any_lastmod[sec] = True
        if is_in_window(url, lastmod):
            counts[sec] = counts.get(sec, 0) + 1
            if lastmod:
                signal[sec] = "lastmod"
            elif sec not in signal:
                signal[sec] = "url-year"
    for sec in counts:
        if signal.get(sec) == "url-year" and section_has_any_lastmod.get(sec):
            signal[sec] = "lastmod"
    return counts, signal


def get_wp_types(client: httpx.Client, base: str) -> tuple[dict | None, str]:
    """Fetch /wp-json/wp/v2/types. Falls back to Wayback if Akamai blocks."""
    types_url = f"{base}/wp-json/wp/v2/types"
    status, text, _ = fetch_text(client, types_url)
    if status == 200 and text.strip().startswith("{"):
        try:
            return json.loads(text), "live"
        except Exception:
            pass
    if status == 403 or status == 0:
        status, text, _ = fetch_via_wayback(client, types_url)
        if status == 200 and text.strip().startswith("{"):
            try:
                return json.loads(text), "wayback"
            except Exception:
                pass
    return None, "unavailable"


def _wp_total(client: httpx.Client, url: str) -> tuple[bool, int]:
    status, text, headers = fetch_text(client, url)
    if status != 200:
        return False, 0
    text = text.strip()
    if not text.startswith("[") and not text.startswith("{"):
        return False, 0
    try:
        body = json.loads(text)
    except Exception:
        return False, 0
    if not isinstance(body, list) or not body:
        return False, 0
    total = 0
    for k in ("X-WP-Total", "x-wp-total"):
        if k in headers:
            try:
                total = int(headers[k])
            except Exception:
                total = 0
            break
    if not total:
        total = len(body)
    return True, total


def confirm_post_type(
    client: httpx.Client, base: str, slug: str, allow_wayback: bool = True
) -> tuple[bool, int, int]:
    """GET /wp-json/wp/v2/{slug}; return (ok, total_count, post_2025_count)."""
    url = f"{base}/wp-json/wp/v2/{slug}?per_page=1"
    ok, total = _wp_total(client, url)
    if not ok and allow_wayback:
        # Wayback can serve cached JSON; only used to confirm existence.
        status, text, headers = fetch_via_wayback(client, url)
        if status == 200 and text.strip().startswith("["):
            ok = True
            total = total or 1
    if not ok:
        return False, 0, 0
    in_window_url = (
        f"{base}/wp-json/wp/v2/{slug}?per_page=1&after=2025-01-01T00:00:00"
    )
    _, in_window = _wp_total(client, in_window_url)
    return True, total, in_window


def load_seeds() -> dict[str, dict]:
    data = json.loads(SEEDS.read_text())
    out: dict[str, dict] = {}
    for m in data["members"]:
        out[m["senator_id"]] = m
    return out


# Manual map: audit report shows display name; seeds use senator_id.
NAME_TO_ID = {
    "John Barrasso": "barrasso-john",
    "Michael F. Bennet": "bennet-michael",
    "Richard Blumenthal": "blumenthal-richard",
    "Christopher A. Coons": "coons-christopher",
    "Catherine Cortez Masto": "masto-catherine",
    "Tom Cotton": "cotton-tom",
    "Mike Crapo": "crapo-mike",
    "Kevin Cramer": "cramer-kevin",
    "Joni Ernst": "ernst-joni",
    "Chuck Grassley": "grassley-chuck",
    "Martin Heinrich": "heinrich-martin",
    "Mazie K. Hirono": "hirono-mazie",
    "Tim Kaine": "kaine-tim",
    "Angus S. King, Jr.": "king-angus",
    "James Lankford": "lankford-james",
    "Roger Marshall": "marshall-roger",
    "Jon Ossoff": "ossoff-jon",
    "Alex Padilla": "padilla-alex",
    "Jack Reed": "reed-jack",
    "James E. Risch": "risch-james",
    "Mike Rounds": "rounds-mike",
    "Bernard Sanders": "sanders-bernard",
    "Tim Scott": "scott-tim",
    "Elizabeth Warren": "warren-elizabeth",
}


def classify_silo(
    client: httpx.Client,
    silo: dict,
    sid: str,
    base: str,
    types: dict | None,
    extras_already: set[tuple[str, str]],
    sitemap_in_window: int = 0,
    sitemap_signal: str = "none",
) -> dict:
    section = silo["section"]
    count = silo["count"]
    silo = {
        **silo,
        "sitemap_in_window": sitemap_in_window,
        "sitemap_signal": sitemap_signal,
    }

    if count < LOW_VALUE_THRESHOLD:
        return {**silo, "senator_id": sid, "classification": "low_value"}

    cands = slug_candidates(section)

    type_slugs: list[str] = []
    if types:
        type_slugs = list(types.keys())

    matched_post_type: str | None = None

    if type_slugs:
        for c in cands:
            if c in type_slugs:
                matched_post_type = c
                break

    wp_total = 0
    wp_in_window = 0
    if not matched_post_type:
        for c in cands:
            ok, total, in_window = confirm_post_type(client, base, c)
            if ok and total >= LOW_VALUE_THRESHOLD:
                matched_post_type = c
                wp_total = total
                wp_in_window = in_window
                break
        else:
            tag = "needs_custom_scraper"
            if sitemap_signal == "none":
                tag = "needs_custom_scraper_unverified"
            elif sitemap_in_window == 0:
                tag = "section_dormant"
            return {
                **silo,
                "senator_id": sid,
                "classification": tag,
                "tried_slugs": cands[:6],
            }
    else:
        ok, wp_total, wp_in_window = confirm_post_type(client, base, matched_post_type)
        if not ok:
            return {
                **silo,
                "senator_id": sid,
                "classification": "needs_custom_scraper",
                "tried_slugs": cands[:6],
                "note": f"types listed {matched_post_type} but endpoint empty",
            }

    base_row = {
        **silo,
        "senator_id": sid,
        "post_type_slug": matched_post_type,
        "wp_total": wp_total,
        "wp_in_window": wp_in_window,
    }
    if (sid, matched_post_type) in extras_already:
        return {**base_row, "classification": "wp_already_collected"}
    if wp_in_window < 5:
        return {**base_row, "classification": "wp_pre_window_only"}
    return {**base_row, "classification": "wp_extras_ready"}


def load_extras_already() -> set[tuple[str, str]]:
    p = ROOT / "pipeline" / "scripts" / "backfill_wp_extras.py"
    text = p.read_text()
    pairs: set[tuple[str, str]] = set()
    for m in re.finditer(r'\("([\w-]+)",\s*"([\w-]+)"\):\s*"\w+"', text):
        pairs.add((m.group(1), m.group(2)))
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--senator", help="senator_id to limit probe to")
    args = ap.parse_args()

    silos = parse_silos(REPORT)
    print(f"parsed {len(silos)} silos from {REPORT.name}")

    seeds = load_seeds()
    extras_already = load_extras_already()
    print(f"existing EXTRAS pairs: {len(extras_already)}")

    by_senator: dict[str, list[dict]] = {}
    for s in silos:
        sid = NAME_TO_ID.get(s["senator_name"])
        if not sid:
            print(f"  ! no id for {s['senator_name']!r}")
            continue
        if args.senator and sid != args.senator:
            continue
        by_senator.setdefault(sid, []).append(s)

    print(f"senators to probe: {len(by_senator)}")

    headers = {"User-Agent": UA, "Accept": "application/json,*/*"}
    results: dict[str, list[dict]] = {}

    with httpx.Client(timeout=20.0, headers=headers) as client:
        for sid, sl in by_senator.items():
            seed = seeds.get(sid)
            if not seed:
                print(f"[{sid}] no seed -- skip")
                continue
            base = (seed.get("official_url") or "").rstrip("/")
            print(f"\n[{sid}] {base}  ({len(sl)} silos)")

            types, types_src = get_wp_types(client, base)
            print(f"  /wp-json/wp/v2/types -> {types_src} ({len(types) if types else 0} types)")

            pairs = fetch_sitemap_lastmods(client, base)
            in_window_by_section, signal_by_section = in_window_counts_by_section(pairs)
            print(
                f"  sitemap walked: {len(pairs)} urls, "
                f"{sum(in_window_by_section.values())} in-window since 2025"
            )

            sl_sorted = sorted(sl, key=lambda x: -x["count"])
            classified: list[dict] = []
            for silo in sl_sorted:
                in_w = in_window_by_section.get(silo["section"], 0)
                sig = signal_by_section.get(silo["section"], "none")
                row = classify_silo(
                    client, silo, sid, base, types, extras_already, in_w, sig
                )
                tag = row["classification"]
                pt = row.get("post_type_slug", "-")
                wp_t = row.get("wp_total", 0)
                wp_w = row.get("wp_in_window", 0)
                sm_w = row.get("sitemap_in_window", 0)
                print(
                    f"    {tag:24s} {silo['section']:40s} pt={pt:20s} "
                    f"sitemap={silo['count']} sm_2025+={sm_w} "
                    f"wp_total={wp_t} wp_2025+={wp_w}"
                )
                classified.append(row)
            results[sid] = classified

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT}")

    counts = {"wp_extras_ready": 0, "wp_already_collected": 0,
              "wp_pre_window_only": 0,
              "needs_custom_scraper": 0,
              "needs_custom_scraper_unverified": 0,
              "section_dormant": 0,
              "low_value": 0}
    for rows in results.values():
        for r in rows:
            counts[r["classification"]] = counts.get(r["classification"], 0) + 1
    print("\n=== classification summary ===")
    for k, v in counts.items():
        print(f"  {k:24s} {v}")


if __name__ == "__main__":
    main()
