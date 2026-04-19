"""
Capitol Releases -- Visual Verification

Screenshots senator listing and detail pages for human review.
Generates a verification report with screenshots showing page
structure, dates, and content. Replicable and documented.

Usage:
    python -m pipeline.commands.visual_verify --senator warren-elizabeth
    python -m pipeline.commands.visual_verify --senator graham-lindsey --detail
    python -m pipeline.commands.visual_verify --all --output pipeline/results/screenshots/
"""

import asyncio
import json
import logging
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Load .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

log = logging.getLogger("capitol.visual")


async def verify_senator(senator: dict, output_dir: Path, include_detail: bool = False):
    """Take screenshots of a senator's listing and detail pages."""
    sid = senator["senator_id"]
    pr_url = senator.get("press_release_url", "")

    if not pr_url:
        log.warning("No press_release_url for %s", sid)
        return None

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    result = {
        "senator_id": sid,
        "press_release_url": pr_url,
        "collection_method": senator.get("collection_method", "?"),
        "screenshots": [],
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }

    senator_dir = output_dir / sid
    senator_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # Screenshot 1: Listing page
        try:
            await page.goto(pr_url, wait_until="networkidle", timeout=20000)
            listing_path = senator_dir / "listing.png"
            await page.screenshot(path=str(listing_path), full_page=False)
            result["screenshots"].append(str(listing_path))
            result["listing_title"] = await page.title()

            # Count items on page
            item_count = await page.evaluate("""() => {
                const selectors = ['article', '.et_pb_post', '.postItem', 'div.element',
                                   '.ArticleBlock', 'div.e-loop-item', '.elementor-post',
                                   'table tbody tr', '.views-row'];
                for (const sel of selectors) {
                    const items = document.querySelectorAll(sel);
                    if (items.length >= 2) return {selector: sel, count: items.length};
                }
                return {selector: 'none', count: 0};
            }""")
            result["listing_items"] = item_count

            log.info("%s listing: %s (%d items via %s)",
                     sid, result["listing_title"][:50],
                     item_count["count"], item_count["selector"])

        except Exception as e:
            log.error("%s listing failed: %s", sid, e)
            result["listing_error"] = str(e)

        # Screenshot 2: Detail page (first press release)
        if include_detail:
            try:
                first_link = await page.evaluate("""() => {
                    const selectors = ['article a[href]', '.et_pb_post a[href]', '.postItem a[href]',
                                       'div.element a[href]', '.ArticleBlock a[href]', 'h2 a[href]', 'h3 a[href]'];
                    for (const sel of selectors) {
                        const links = document.querySelectorAll(sel);
                        for (const link of links) {
                            const href = link.href;
                            if (href && href.includes('senate.gov') && link.textContent.trim().length > 15) {
                                return href;
                            }
                        }
                    }
                    return null;
                }""")

                if first_link:
                    await page.goto(first_link, wait_until="networkidle", timeout=20000)
                    detail_path = senator_dir / "detail.png"
                    await page.screenshot(path=str(detail_path), full_page=False)
                    result["screenshots"].append(str(detail_path))
                    result["detail_url"] = first_link
                    result["detail_title"] = await page.title()
                    log.info("%s detail: %s", sid, result["detail_title"][:50])
            except Exception as e:
                log.error("%s detail failed: %s", sid, e)
                result["detail_error"] = str(e)

        await browser.close()

    # Save result JSON
    result_path = senator_dir / "verification.json"
    result_path.write_text(json.dumps(result, indent=2))

    return result


async def verify_all(senators: list[dict], output_dir: Path, include_detail: bool = False):
    """Verify all senators sequentially (to avoid overwhelming sites)."""
    results = []
    for senator in senators:
        result = await verify_senator(senator, output_dir, include_detail)
        if result:
            results.append(result)
        await asyncio.sleep(1.0)  # politeness

    # Write summary report
    summary = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "with_items": sum(1 for r in results if r.get("listing_items", {}).get("count", 0) > 0),
        "failed": sum(1 for r in results if "listing_error" in r),
        "results": results,
    }
    summary_path = output_dir / "verification_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info("Summary saved to %s", summary_path)

    print(f"\n{'='*60}")
    print(f"  VISUAL VERIFICATION SUMMARY")
    print(f"{'='*60}")
    print(f"  Total: {summary['total']}")
    print(f"  With items: {summary['with_items']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Screenshots: {output_dir}")
    print(f"{'='*60}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Visual verification of senator pages")
    parser.add_argument("--senator", help="Verify specific senator")
    parser.add_argument("--all", action="store_true", help="Verify all senators")
    parser.add_argument("--detail", action="store_true", help="Also screenshot detail pages")
    parser.add_argument("--output", default="pipeline/results/screenshots",
                        help="Output directory for screenshots")
    parser.add_argument("--method", choices=["rss", "httpx", "playwright"],
                        help="Only verify senators using this method")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load senators
    from pipeline.lib.seeds import load_members
    senators = load_members()

    if args.senator:
        senators = [s for s in senators if s["senator_id"] == args.senator]
    if args.method:
        senators = [s for s in senators if s.get("collection_method") == args.method]

    if not senators:
        print("No senators matched")
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    asyncio.run(verify_all(senators, output_dir, args.detail))


if __name__ == "__main__":
    main()
