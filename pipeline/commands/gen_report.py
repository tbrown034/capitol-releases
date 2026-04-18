"""Generate the per-senator intelligence report."""

import json
import os
from datetime import datetime
from pathlib import Path

# Load .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import psycopg2

DB_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # Load seed config
    seed_path = Path(__file__).resolve().parent.parent / "seeds" / "senate.json"
    data = json.loads(seed_path.read_text())
    senators = {m["senator_id"]: m for m in data["members"]}

    # DB stats per senator
    cur.execute("""
        SELECT senator_id,
               COUNT(*) as total,
               COUNT(*) FILTER (WHERE deleted_at IS NULL) as active,
               COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) as deleted,
               COUNT(*) FILTER (WHERE published_at IS NOT NULL AND deleted_at IS NULL) as dated,
               COUNT(*) FILTER (WHERE body_text IS NOT NULL AND length(body_text) > 50 AND deleted_at IS NULL) as with_body,
               MIN(published_at) FILTER (WHERE deleted_at IS NULL) as earliest,
               MAX(published_at) FILTER (WHERE deleted_at IS NULL) as latest,
               COUNT(*) FILTER (WHERE date_source IS NOT NULL AND deleted_at IS NULL) as with_provenance
        FROM press_releases
        GROUP BY senator_id
        ORDER BY senator_id
    """)
    db_stats = {}
    for row in cur.fetchall():
        db_stats[row[0]] = {
            "total": row[1], "active": row[2], "deleted": row[3],
            "dated": row[4], "with_body": row[5],
            "earliest": row[6], "latest": row[7],
            "with_provenance": row[8],
        }

    # Health check results
    cur.execute("""
        SELECT DISTINCT ON (senator_id) senator_id, passed, url_status, items_found, page_load_ms, error_message
        FROM health_checks ORDER BY senator_id, checked_at DESC
    """)
    health = {}
    for row in cur.fetchall():
        health[row[0]] = {"passed": row[1], "status": row[2], "items": row[3], "ms": row[4], "error": row[5]}

    # RSS discovery results
    rss_path = Path(__file__).resolve().parent.parent / "results" / "rss_discovery.json"
    rss_data = json.loads(rss_path.read_text())
    rss_map = {r["senator_id"]: r for r in rss_data["found"]}

    cur.close()
    conn.close()

    # Build report
    lines = []
    w = lines.append

    w("# Capitol Releases: Per-Senator Intelligence Report")
    w("")
    w(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} ET")
    w("")
    w("This document captures everything learned about each senator's web presence,")
    w("scraping challenges, edge cases, and the recommended collection strategy.")
    w("It is the institutional knowledge that makes the scraping pipeline replicable.")
    w("")
    w("---")
    w("")
    w("## Summary")
    w("")
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Total senators in config | {len(senators)} |")
    w(f"| Senators with data | {len(db_stats)} |")

    method_counts = {}
    for s in senators.values():
        m = s.get("collection_method", "unset")
        method_counts[m] = method_counts.get(m, 0) + 1
    for m, c in sorted(method_counts.items(), key=lambda x: -x[1]):
        w(f"| Collection method: {m} | {c} |")

    rss_with_items = sum(1 for r in rss_data["found"] if r["item_count"] > 0)
    w(f"| RSS feeds discovered | {len(rss_data['found'])} (with items: {rss_with_items}) |")
    w("| RSS feeds reliable | 24 |")
    w("")

    # Parser families
    families = {}
    for s in senators.values():
        f = s.get("parser_family", "unknown")
        families[f] = families.get(f, 0) + 1
    w("## CMS / Parser Families")
    w("")
    w("| Family | Count | Notes |")
    w("|--------|-------|-------|")
    w(f"| senate-wordpress | {families.get('senate-wordpress', 0)} | Most common. Usually has RSS. Selectors: article.et_pb_post, article.postItem, .elementor-post |")
    w(f"| senate-generic | {families.get('senate-generic', 0)} | Senate legacy CMS. Selectors: div.element, .ArticleBlock. Some JS-rendered. |")
    w(f"| senate-coldfusion | {families.get('senate-coldfusion', 0)} | /public/index.cfm/ URLs. Table layout. Dates only on listing page, not detail. |")
    w(f"| senate-drupal | {families.get('senate-drupal', 0)} | Rare. |")
    w("")

    # Edge cases
    w("## Known Edge Cases and Lessons Learned")
    w("")

    w("### 1. JS-Rendered Sites (8 senators)")
    w("These load press releases via AJAX. Static HTTP gets an empty js-content div.")
    w("Need Playwright or RSS as collection method.")
    w("")
    w("| Senator | Why | Fix |")
    w("|---------|-----|-----|")
    w("| Reed (D-RI) | senate-generic, empty js-content | Playwright or RSS |")
    w("| Capito (R-WV) | senate-generic, empty js-content | Playwright |")
    w("| Cotton (R-AR) | senate-generic, empty js-content | Playwright |")
    w("| Markey (D-MA) | senate-generic, empty js-content | Playwright |")
    w("| Schmitt (R-MO) | JetEngine AJAX pagination | Playwright (has RSS but 0 items) |")
    w("| Whitehouse (D-RI) | JetEngine AJAX pagination | Has RSS feed |")
    w("| Young (R-IN) | JetEngine AJAX pagination | Has RSS feed |")
    w("| Booker (D-NJ) | senate-generic, JS-rendered | Playwright |")
    w("| Ossoff (D-GA) | Elementor AJAX pagination | Has RSS feed (10 items) |")
    w("| Merkley (D-OR) | WordPress, JS pagination | Has RSS feed |")
    w("")

    w("### 2. ColdFusion Date Problem")
    w("ColdFusion senators (Graham, Klobuchar, McConnell, Kennedy, Moran, Boozman, Thune, Fischer)")
    w("have dates on the listing page in td.recordListDate (e.g., '4/7/26') but NOT on detail pages.")
    w("No meta tags, no JSON-LD, no time elements on detail pages.")
    w("")
    w("**Lesson:** Must extract dates during listing-page scrape and pass them to the insert,")
    w("not rely on detail-page extraction. The current pipeline extracts dates from listing items")
    w("in extract_item_data(), which handles this correctly for new scrapes.")
    w("")

    w("### 3. Meta Tag Variations")
    w("We initially only searched for article:published_time and datePublished.")
    w("King's 899 null dates were fixed by adding meta name='date' to the search.")
    w("")
    w("Tags found in the wild:")
    w("- article:published_time (OpenGraph standard)")
    w("- og:article:published_time")
    w("- datePublished (Schema.org)")
    w("- date (simple, used by King and others)")
    w("- DC.date.issued (Dublin Core)")
    w("- pubdate")
    w("")

    w("### 4. Body Text Extraction Failures")
    w("WordPress Divi sites (Hickenlooper, Kim, Moody) render body text via JS.")
    w("The .post-content selector finds an element but it only has ~20 chars.")
    w("The actual content is in the DOM but needs JS rendering.")
    w("")
    w("**Fix used:** Aggressive paragraph extraction -- collect all p tags with >20 chars")
    w("and join them. Also tried heading-based isolation: find h1, take all text after it.")
    w("Both work for getting content from partially-rendered pages.")
    w("")

    w("### 5. Nav Link Contamination")
    w("The selector logic sometimes picks up navigation links instead of press releases.")
    w("Common junk patterns:")
    w("- /about, /contact, /services, /issues/*")
    w("- Committee assignments, flag requests, tour requests")
    w("- Social media links (twitter, facebook, bsky)")
    w("- Photo galleries, weekly columns, audio statements")
    w("- Listing page URLs ending in /press-releases/ (no slug)")
    w("")
    w("**Prevention:** test_no_navigation_urls and test_no_listing_page_urls catch these.")
    w("~211 junk records cleaned in the April 17 session.")
    w("")

    w("### 6. RSS Feed Gotchas")
    w("- WordPress comment feeds at /press-releases/feed/ return valid RSS with 0 items (Gillibrand)")
    w("- wp-json/oembed endpoints look like XML but are not RSS feeds (Cassidy, Risch, Schiff, Warner)")
    w("- Broad feeds (/feed/) include all post types, not just press releases")
    w("- Warren's /rss/ returns 50 items including videos -- needs content classification")
    w("- 14 of 52 discovered feeds were false positives, leaving 38 reliable")
    w("- After health check, 14 more demoted (0 items), leaving 24 as primary collection method")
    w("")

    w("### 7. Date at Character 720+")
    w("ColdFusion sites have ~700 characters of navigation text before the first date.")
    w("Our body-text date search initially only looked at the first 500 characters.")
    w("Expanding to 1000 characters fixed Graham and similar senators.")
    w("")

    w("### 8. URL Path Inconsistencies")
    w("- Some senators use /press-releases/, others /press_releases/ (underscore)")
    w("- Bennet's seed URL pointed to a 2014 UUID path, not the listing page")
    w("- Welch's seed URL pointed to /press-kit/ (contact info), not /category/press-release/")
    w("- ColdFusion URLs use GUIDs: /press-releases?ID=70C386B4-7762-45E6-968D-C40EFAFD993B")
    w("")

    w("### 9. Pagination Patterns (6 types found)")
    w("1. rel='next' link (standard, most reliable)")
    w("2. Text-based ('Next >', 'Older Entries', '>>')")
    w("3. WordPress path-segment (/page/2/, /page/3/)")
    w("4. Query parameter (?page=2, ?pagenum_rs=2)")
    w("5. Elementor custom (?e-page-f7b8172=2)")
    w("6. AJAX/JS click-based (JetEngine -- requires Playwright)")
    w("")

    w("### 10. Armstrong Exception")
    w("Alan Armstrong (R-OK) is a new senator. His press releases page exists")
    w("(WordPress archive page with heading) but div.page-content is completely empty.")
    w("No releases published yet. Monitor and collect once content appears.")
    w("")

    w("---")
    w("")
    w("## Ideas for Ongoing Collection Per Senator")
    w("")
    w("### RSS senators (24) -- lowest maintenance")
    w("Parse the feed, fetch detail pages for body text. No selector maintenance.")
    w("Run health check weekly to verify feed still has items.")
    w("If feed breaks, fall back to httpx collector.")
    w("")
    w("### httpx senators (68) -- moderate maintenance")
    w("Selector-based scraping. Robust across 8+ CMS patterns.")
    w("Weekly drift detection: verify selector still finds items on listing page.")
    w("If selector breaks, use AI to propose new selectors from page structure.")
    w("ColdFusion senators: always extract dates from listing page, not detail.")
    w("")
    w("### Playwright senators (8) -- highest maintenance")
    w("JS-rendered sites need headless browser. Slower, more resource-intensive.")
    w("Check if RSS feed becomes available (some may add it later).")
    w("For daily updates, page 1 only (minimize browser time).")
    w("For backfill, click through AJAX pagination.")
    w("")
    w("### AI-assisted quality layer (all senators)")
    w("Post-collection Claude Haiku validation:")
    w("- Is this a real press release or nav boilerplate?")
    w("- Is the date plausible?")
    w("- Is the content type classification correct?")
    w("- Does the body text look like actual content?")
    w("Advisory only. Flag for review, never auto-modify.")
    w("")

    w("---")
    w("")
    w("## Per-Senator Detail")
    w("")

    sorted_senators = sorted(senators.values(), key=lambda s: (s["state"], s["full_name"]))

    for s in sorted_senators:
        sid = s["senator_id"]
        stats = db_stats.get(sid, {})
        hc = health.get(sid, {})
        rss = rss_map.get(sid, {})

        w(f"### {s['full_name']} ({s['party']}-{s['state']})")
        w("")
        w(f"- **ID:** {sid}")
        w(f"- **URL:** {s.get('press_release_url', 'none')}")
        w(f"- **Parser family:** {s.get('parser_family', 'unknown')}")
        w(f"- **Collection method:** {s.get('collection_method', 'unset')}")
        w(f"- **Confidence:** {s.get('confidence', 0):.0%}")
        w(f"- **Requires JS:** {s.get('requires_js', False)}")

        if s.get("rss_feed_url"):
            w(f"- **RSS feed:** {s['rss_feed_url']}")

        if stats:
            active = stats["active"]
            dated_pct = f"{stats['dated']/active*100:.0f}%" if active > 0 else "n/a"
            body_pct = f"{stats['with_body']/active*100:.0f}%" if active > 0 else "n/a"
            earliest = stats["earliest"].strftime("%Y-%m-%d") if stats["earliest"] else "none"
            latest = stats["latest"].strftime("%Y-%m-%d") if stats["latest"] else "none"
            w(f"- **Records:** {active} active, {stats['deleted']} deleted")
            w(f"- **Dated:** {dated_pct} | **Body text:** {body_pct}")
            w(f"- **Date range:** {earliest} to {latest}")
            if stats["with_provenance"] > 0:
                w(f"- **Date provenance:** {stats['with_provenance']} records")
        else:
            w("- **Records:** 0")

        if hc:
            status = "PASS" if hc["passed"] else "FAIL"
            items = hc.get("items") or 0
            ms = hc.get("ms") or 0
            w(f"- **Health check:** {status} (HTTP {hc.get('status', '?')}, {items} items, {ms}ms)")

        notes = s.get("notes", "")
        if notes:
            w(f"- **Notes:** {notes}")

        w("")

    report = "\n".join(lines)
    output_path = Path(__file__).resolve().parent.parent.parent / "docs" / "senator-intelligence-report.md"
    output_path.write_text(report)
    print(f"Report written: {len(lines)} lines, {len(report):,} chars")
    print(f"Covers {len(sorted_senators)} senators")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
