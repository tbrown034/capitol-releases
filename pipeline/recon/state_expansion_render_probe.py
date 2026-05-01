"""Render probe for the state expansion source inventory.

This is a research artifact generator. It uses Playwright to load selected
source pages in Chromium and records whether rendered DOM content differs
materially from the raw HTTP probe.

Outputs:
  docs/state-expansion-render-probe-2026-05-01.json
  docs/state-expansion-render-probe-2026-05-01.md
  pipeline/recon/state_expansion_render_probe_2026_05_01.json
  pipeline/recon/state_expansion_render_probe_2026_05_01.md
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
INVENTORY_JSON = ROOT / "pipeline" / "recon" / "state_expansion_source_inventory_2026_05_01.json"
DEFAULT_DOCS_JSON = ROOT / "docs" / "state-expansion-render-probe-2026-05-01.json"
DEFAULT_DOCS_MD = ROOT / "docs" / "state-expansion-render-probe-2026-05-01.md"
DEFAULT_TRACKED_JSON = ROOT / "pipeline" / "recon" / "state_expansion_render_probe_2026_05_01.json"
DEFAULT_TRACKED_MD = ROOT / "pipeline" / "recon" / "state_expansion_render_probe_2026_05_01.md"

DATE_RE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+\d{4})\b",
    re.I,
)

CARD_SELECTORS = [
    "article",
    ".post",
    ".entry",
    ".views-row",
    ".news-item",
    ".press-release",
    ".jet-listing-grid__item",
    "[class*='card']",
    "[class*='result']",
    "tr",
]


def should_probe(row: dict) -> bool:
    if row["listing_url"] == "UNKNOWN_NEEDS_PROFILE":
        return False
    if row["implementation_status"] in {"ready_first_wave", "implemented_needs_hardening"}:
        return True
    cms = row.get("cms_family") or ""
    if cms in {"sharepoint", "aspnet", "civicplus", "mixed", "unknown_static_or_cms"}:
        return True
    url = row.get("listing_url", "")
    return any(token in url.lower() for token in [".aspx", ".cfm", "sharepoint", "civicplus"])


def compact_links(page, limit: int = 20) -> list[dict[str, str]]:
    return page.evaluate(
        """limit => Array.from(document.querySelectorAll('a[href]'))
            .map(a => ({ text: (a.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 120),
                         href: new URL(a.getAttribute('href'), location.href).href }))
            .filter(a => a.text && a.href.startsWith('http'))
            .slice(0, limit)""",
        limit,
    )


def selector_counts(page) -> dict[str, int]:
    counts: dict[str, int] = {}
    for selector in CARD_SELECTORS:
        try:
            count = page.locator(selector).count()
        except Exception:
            count = 0
        if count:
            counts[selector] = count
    return counts


def probe_one(page, row: dict) -> dict:
    url = row["listing_url"]
    result = {
        "source_id": row["source_id"],
        "state": row["state"],
        "office_scope": row["office_scope"],
        "url": url,
        "raw_http_status": (row.get("evidence") or {}).get("http_status"),
        "raw_text_chars": (row.get("evidence") or {}).get("text_chars"),
        "raw_date_match_count": (row.get("evidence") or {}).get("date_match_count"),
    }
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
        try:
            page.wait_for_load_state("networkidle", timeout=7000)
        except PlaywrightTimeoutError:
            pass

        text = page.locator("body").inner_text(timeout=5000)
        title = page.title()
        links = compact_links(page)
        dates = DATE_RE.findall(text[:80000])
        raw_chars = result.get("raw_text_chars") or 0
        rendered_chars = len(text)
        result.update(
            {
                "render_status": "ok",
                "http_status": response.status if response else None,
                "final_url": page.url,
                "page_title": title,
                "rendered_text_chars": rendered_chars,
                "rendered_date_match_count": len(dates),
                "first_dates": dates[:8],
                "link_count": len(links),
                "sample_links": links[:10],
                "selector_counts": selector_counts(page),
                "material_render_delta": (
                    raw_chars == 0
                    or rendered_chars > raw_chars * 1.25
                    or len(dates) > (result.get("raw_date_match_count") or 0) + 3
                ),
                "host": urlparse(page.url).netloc,
            }
        )
    except Exception as exc:
        result.update(
            {
                "render_status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    return result


def render_markdown(results: list[dict]) -> str:
    ok = [r for r in results if r["render_status"] == "ok"]
    errors = [r for r in results if r["render_status"] != "ok"]
    deltas = [r for r in ok if r.get("material_render_delta")]
    lines = [
        "# State Expansion Render Probe",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        f"- Probed URLs: {len(results)}",
        f"- Browser successes: {len(ok)}",
        f"- Browser errors: {len(errors)}",
        f"- Material render deltas: {len(deltas)}",
        "",
        "## Results",
        "",
        "| Source | Scope | Status | Raw chars | Rendered chars | Dates | Likely row selectors | URL |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for r in results:
        selectors = ", ".join(f"{k}={v}" for k, v in (r.get("selector_counts") or {}).items())
        lines.append(
            "| `{source}` | {scope} | {status} | {raw} | {rendered} | {dates} | {selectors} | {url} |".format(
                source=r["source_id"],
                scope=r["office_scope"],
                status=r["render_status"],
                raw=r.get("raw_text_chars") or "",
                rendered=r.get("rendered_text_chars") or "",
                dates=r.get("rendered_date_match_count") or "",
                selectors=selectors[:160],
                url=r["url"],
            )
        )
    if errors:
        lines.extend(["", "## Errors", ""])
        for r in errors:
            lines.append(f"- `{r['source_id']}`: {r.get('error', 'unknown error')}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument(
        "--label",
        default="",
        help="Optional output label, e.g. sos, to avoid overwriting the default broad probe.",
    )
    args = parser.parse_args()

    rows = json.loads(INVENTORY_JSON.read_text())
    selected = [r for r in rows if should_probe(r)]
    if args.source_id:
        wanted = set(args.source_id)
        selected = [r for r in rows if r["source_id"] in wanted]
    selected = selected[: args.limit]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
        )
        results = []
        for row in selected:
            page = context.new_page()
            try:
                results.append(probe_one(page, row))
            finally:
                page.close()
        context.close()
        browser.close()

    rendered_json = json.dumps(results, indent=2, ensure_ascii=False) + "\n"
    rendered_md = render_markdown(results)
    if args.label:
        safe = re.sub(r"[^a-z0-9_]+", "_", args.label.lower()).strip("_")
        docs_json = ROOT / "docs" / f"state-expansion-render-probe-{safe}-2026-05-01.json"
        docs_md = ROOT / "docs" / f"state-expansion-render-probe-{safe}-2026-05-01.md"
        tracked_json = ROOT / "pipeline" / "recon" / f"state_expansion_render_probe_{safe}_2026_05_01.json"
        tracked_md = ROOT / "pipeline" / "recon" / f"state_expansion_render_probe_{safe}_2026_05_01.md"
    else:
        docs_json = DEFAULT_DOCS_JSON
        docs_md = DEFAULT_DOCS_MD
        tracked_json = DEFAULT_TRACKED_JSON
        tracked_md = DEFAULT_TRACKED_MD
    docs_json.write_text(rendered_json)
    tracked_json.write_text(rendered_json)
    docs_md.write_text(rendered_md)
    tracked_md.write_text(rendered_md)


if __name__ == "__main__":
    main()
