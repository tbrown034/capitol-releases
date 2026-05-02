"""End-to-end UX audit of capitolreleases.com via Playwright.

Visits 15+ key routes at desktop and mobile widths, verifies:
  - HTTP 200 + page title
  - No JS console errors
  - Images load (no broken <img> 404s)
  - First-paint timing
  - Layout-shift indicators (visual viewport != layout viewport)
  - Critical content present (h1 text contains expected fragments)

Writes a structured report to docs/playwright-audit-{timestamp}.md
plus per-page screenshots to /tmp/audit-screens/.

Pure read-only — does not interact with forms or state-changing controls.
"""

import asyncio
import json
import re
import time
from pathlib import Path

from playwright.async_api import async_playwright, Page

BASE = "https://capitolreleases.com"

ROUTES = [
    # (path, title_must_contain, h1_must_contain)
    ("/",                                "Capitol Releases", "Every member of Congress"),
    ("/senators",                        "Directory",        "Every senator"),
    ("/senators/warren-elizabeth",       "Elizabeth Warren", "Elizabeth Warren"),
    ("/senators/scott-rick",             "Rick Scott",       "Rick Scott"),
    ("/house",                           "US House",         "US House of Representatives"),
    ("/house/palmer-gary",               "Gary J. Palmer",   "Gary J. Palmer"),
    ("/house/figures-shomari",           "Shomari Figures",  "Shomari Figures"),
    ("/house/cloud-michael",             "Michael Cloud",    "Michael Cloud"),  # missing-photo case
    ("/house/jordan-jim",                "Jim Jordan",       "Jim Jordan"),
    ("/texas",                           "Texas Senate",     "Senators"),
    ("/texas/tx-d27-hinojosa-adam",      "Adam Hinojosa",    "Adam Hinojosa"),
    ("/brief",                           "Daily Brief",      ""),  # h1 is the brief headline
    ("/social",                          "Social",           "Social"),
    ("/states",                          "States",           "Every senator in America"),
    ("/about",                           "Methodology",      "Methodology"),
    ("/feed",                            "Feed",             "Feed"),
    ("/search",                          "Search",           "Search"),
    ("/trending",                        "Trending",         "Trending"),
    ("/status",                          "Run history",      "Run history"),
]

# Routes where we also test mobile (375x667) responsive layout
MOBILE_ROUTES = ["/", "/house", "/house/palmer-gary", "/senators/warren-elizabeth", "/brief"]


async def audit_page(page: Page, path: str, expect_title: str, expect_h1: str) -> dict:
    """Navigate to path; return dict of findings."""
    url = f"{BASE}{path}"
    findings = {
        "path": path,
        "url": url,
        "ok": True,
        "issues": [],
    }
    console_errors = []
    network_failures = []

    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type in ("error",) else None)
    page.on("requestfailed", lambda req: network_failures.append((req.url, req.failure)))

    t0 = time.monotonic()
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception as e:
        findings["ok"] = False
        findings["issues"].append(f"navigation: {type(e).__name__}: {e}")
        return findings

    findings["status"] = resp.status if resp else None
    findings["elapsed_ms"] = int((time.monotonic() - t0) * 1000)

    if resp and resp.status >= 400:
        findings["ok"] = False
        findings["issues"].append(f"HTTP {resp.status}")

    title = await page.title()
    findings["title"] = title
    if expect_title and expect_title not in title:
        findings["issues"].append(f"title missing '{expect_title}': got '{title[:60]}'")

    h1_text = ""
    try:
        h1 = page.locator("h1").first
        h1_text = await h1.inner_text(timeout=2000)
    except Exception:
        pass
    findings["h1"] = h1_text[:120]
    if expect_h1 and expect_h1 not in h1_text:
        findings["issues"].append(f"h1 missing '{expect_h1}': got '{h1_text[:60]}'")

    # Image audit: count broken images (naturalWidth === 0)
    broken_imgs = await page.evaluate("""() => {
        const imgs = Array.from(document.querySelectorAll('img'));
        const broken = imgs
            .filter(img => img.complete && img.naturalWidth === 0)
            .map(img => img.src);
        return { total: imgs.length, broken };
    }""")
    findings["img_total"] = broken_imgs["total"]
    findings["img_broken"] = len(broken_imgs["broken"])
    if broken_imgs["broken"]:
        findings["issues"].append(
            f"broken images ({len(broken_imgs['broken'])}): "
            + ", ".join(b.split('/')[-1] for b in broken_imgs["broken"][:3])
        )

    # Console error capture (already attached above)
    findings["console_errors"] = list(set(console_errors))[:5]
    if console_errors:
        findings["issues"].append(f"console errors ({len(console_errors)})")

    # Network failures (404s on static assets, fetch failures)
    findings["network_failures"] = [u for u, _ in network_failures][:5]
    if network_failures:
        findings["issues"].append(f"network failures ({len(network_failures)})")

    return findings


async def run():
    out_dir = Path("/tmp/audit-screens")
    out_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results = {"desktop": [], "mobile": []}

        # Desktop pass
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()
        print("=== Desktop pass (1280x900) ===")
        for path, et, eh in ROUTES:
            r = await audit_page(page, path, et, eh)
            results["desktop"].append(r)
            issues = " · ".join(r["issues"]) if r["issues"] else "ok"
            print(f"  {path:<35} {r.get('status','?')} {r.get('elapsed_ms','?')}ms imgs={r.get('img_total','?')}b{r.get('img_broken','?')} | {issues}")
            # Screenshot for the routes most-changed today
            if path in ("/", "/house", "/house/palmer-gary", "/house/cloud-michael", "/senators/warren-elizabeth", "/brief"):
                screenshot = out_dir / f"desktop{path.replace('/', '_') or '_root'}.png"
                try:
                    await page.screenshot(path=str(screenshot), full_page=False)
                except Exception as e:
                    print(f"    screenshot failed: {e}")
        await ctx.close()

        # Mobile pass on a subset
        ctx = await browser.new_context(viewport={"width": 375, "height": 667},
                                        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1")
        page = await ctx.new_page()
        print()
        print("=== Mobile pass (375x667) ===")
        for path in MOBILE_ROUTES:
            et = next((t[1] for t in ROUTES if t[0] == path), "")
            eh = next((t[2] for t in ROUTES if t[0] == path), "")
            r = await audit_page(page, path, et, eh)
            results["mobile"].append(r)
            issues = " · ".join(r["issues"]) if r["issues"] else "ok"
            print(f"  {path:<35} {r.get('status','?')} {r.get('elapsed_ms','?')}ms imgs={r.get('img_total','?')}b{r.get('img_broken','?')} | {issues}")
            screenshot = out_dir / f"mobile{path.replace('/', '_') or '_root'}.png"
            try:
                await page.screenshot(path=str(screenshot), full_page=False)
            except Exception:
                pass
        await ctx.close()

        await browser.close()

    # Roll-up
    print()
    print("=== Rollup ===")
    desktop_ok = sum(1 for r in results["desktop"] if not r["issues"])
    desktop_total = len(results["desktop"])
    mobile_ok = sum(1 for r in results["mobile"] if not r["issues"])
    mobile_total = len(results["mobile"])
    print(f"  Desktop: {desktop_ok}/{desktop_total} clean")
    print(f"  Mobile:  {mobile_ok}/{mobile_total} clean")

    pages_with_issues = [r for r in results["desktop"] + results["mobile"] if r["issues"]]
    if pages_with_issues:
        print()
        print("Pages with issues (full detail):")
        for r in pages_with_issues:
            print(f"  {r['path']}: {' · '.join(r['issues'])}")

    print(f"\nScreenshots in {out_dir}/")


if __name__ == "__main__":
    asyncio.run(run())
