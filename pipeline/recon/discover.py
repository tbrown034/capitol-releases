"""
Senate/House press-release recon script.

Probes each member's official website to discover press-release sections,
classify CMS/parser families, detect pagination, extract CSS selectors,
and output an enriched seed config.

Usage:
    python discover.py --chamber senate
    python discover.py --chamber house
    python discover.py --chamber both
"""

import asyncio
import json
import re
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

# house.gov blocks custom UAs with 403. Use a browser-like UA for all sites.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# Concurrency: polite but not glacial
MAX_CONCURRENT = 12
REQUEST_TIMEOUT = 20.0

# URL patterns to probe for press-release index pages, ordered by likelihood.
PRESS_RELEASE_PATHS = [
    "/newsroom/press-releases",
    "/news/press-releases",
    "/media/press-releases",
    "/media-center/press-releases",
    "/press-releases",
    "/newsroom/press",
    "/newsroom",
    "/news",
    "/media",
    "/media-center",
    # ColdFusion sites (Senate legacy CMS, ~10% of offices)
    "/public/index.cfm/press-releases",
    "/public/index.cfm/news-releases",
    "/public/index.cfm/pressreleases",
    "/public/index.cfm/news",
    "/public/index.cfm/newsroom",
    # Other variants
    "/public/press-releases",
    "/public/news-releases",
    "/press/press-releases",
    # House-specific patterns
    "/news/documentquery.aspx?DocumentTypeID=27",
    "/media/press-releases",
]

# ----- CMS / parser family detection -----

def detect_cms(html: str, soup: BeautifulSoup) -> str:
    """Fingerprint the CMS from HTML source."""
    html_lower = html[:5000].lower()

    # WordPress indicators
    if "wp-content" in html_lower or "wp-json" in html_lower:
        return "wordpress"
    meta_gen = soup.find("meta", attrs={"name": "generator"})
    if meta_gen and "wordpress" in str(meta_gen.get("content", "")).lower():
        return "wordpress"

    # Drupal indicators
    if "drupal" in html_lower or 'data-drupal' in html_lower:
        return "drupal"
    if soup.find(attrs={"class": re.compile(r"drupal|views-row")}):
        return "drupal"

    # ColdFusion (legacy Senate CMS)
    if "index.cfm" in html_lower or "coldfusion" in html_lower:
        return "coldfusion"

    # Senate shared platform (custom CMS used by many offices)
    if "fireside21" in html_lower or "sos_widget" in html_lower:
        return "fireside"

    # Look for React/Vue SPA indicators
    if re.search(r'id=["\'](?:app|root|__next)["\']', html_lower):
        body_text = soup.body.get_text(strip=True) if soup.body else ""
        if len(body_text) < 200:
            return "js-spa"

    return "unknown"


def classify_parser_family(cms: str, selectors: dict, url: str) -> str:
    """Map CMS + structural signals to a parser family name."""
    if cms == "js-spa":
        return "js-rendered"
    if cms == "wordpress":
        return "senate-wordpress"
    if cms == "drupal":
        return "senate-drupal"
    if cms == "coldfusion":
        return "senate-coldfusion"
    if cms == "fireside":
        return "senate-fireside"
    return "senate-generic"


# ----- Selector extraction -----

# Common list-item patterns on Senate press-release pages.
LIST_ITEM_CANDIDATES = [
    # Specific press-release list patterns
    "table.table-striped tbody tr",
    ".views-row",
    ".element-list .element",
    ".list-item",
    ".newsroom-result",
    "article.post",
    ".media-body",
    "li.press-release",
    ".record",
    # Generic but common
    ".content-list li",
    "ul.listing li",
    ".news-list li",
    "#press .item",
    "#newscontent .item",
    ".entry",
]


def extract_selectors(soup: BeautifulSoup, base_url: str) -> dict:
    """Try to discover the repeated list-item pattern and its sub-selectors."""
    result = {
        "list_item": None,
        "title": None,
        "date": None,
        "detail_link": None,
    }

    # Strategy 1: try known candidate selectors
    for candidate in LIST_ITEM_CANDIDATES:
        items = soup.select(candidate)
        if len(items) >= 3:
            result["list_item"] = candidate
            # Try to find title/link/date within the first item
            first = items[0]
            _extract_sub_selectors(first, result, base_url)
            return result

    # Strategy 2: find the largest repeated element pattern
    result["list_item"], first_item = _find_repeated_pattern(soup)
    if first_item:
        _extract_sub_selectors(first_item, result, base_url)

    return result


def _extract_sub_selectors(item, result: dict, base_url: str):
    """Given a single list item element, try to find title, date, link."""
    # Title: first <a> with substantial text, or first heading
    for tag in ["h2 a", "h3 a", "h4 a", "a"]:
        el = item.select_one(tag)
        if el and len(el.get_text(strip=True)) > 10:
            result["title"] = tag
            href = el.get("href", "")
            if href and href != "#":
                result["detail_link"] = tag + "[href]"
            break

    # If no title link found, try headings without links
    if not result["title"]:
        for tag in ["h2", "h3", "h4"]:
            el = item.select_one(tag)
            if el and len(el.get_text(strip=True)) > 5:
                result["title"] = tag
                break

    # Date: look for time elements, .date class, or date-like text
    time_el = item.select_one("time")
    if time_el:
        result["date"] = "time"
        return

    for cls in ["date", "datetime", "timestamp", "post-date", "entry-date"]:
        el = item.select_one(f".{cls}")
        if el:
            result["date"] = f".{cls}"
            return

    # Look for any element with date-like text
    date_pattern = re.compile(
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}|"
        r"\d{1,2}/\d{1,2}/\d{2,4}|"
        r"\d{4}-\d{2}-\d{2}"
    )
    for el in item.find_all(True):
        text = el.get_text(strip=True)
        if date_pattern.search(text) and len(text) < 50:
            classes = el.get("class", [])
            if classes:
                result["date"] = f".{classes[0]}"
            elif el.name == "span":
                result["date"] = "span"
            elif el.name == "td":
                result["date"] = "td"
            break


def _find_repeated_pattern(soup: BeautifulSoup):
    """Find the container with the most repeated child element patterns."""
    best_selector = None
    best_count = 0
    best_item = None

    main = soup.select_one("main") or soup.select_one("#main") or soup.select_one(".main-content") or soup.body
    if not main:
        return None, None

    for container in main.find_all(True, recursive=True):
        children = [c for c in container.children if hasattr(c, "name") and c.name]
        if len(children) < 3:
            continue
        # Check if children share a tag name and class
        tag_counts = {}
        for child in children:
            key = child.name + "." + ".".join(child.get("class", []))
            tag_counts.setdefault(key, []).append(child)
        for key, items in tag_counts.items():
            if len(items) >= 3 and len(items) > best_count:
                # Build a CSS selector for this pattern
                parts = key.split(".")
                tag = parts[0]
                classes = [c for c in parts[1:] if c]
                selector = tag + "".join(f".{c}" for c in classes) if classes else tag
                # Verify these items contain links (likely press releases)
                has_links = sum(1 for i in items if i.find("a"))
                if has_links >= len(items) * 0.5:
                    best_count = len(items)
                    best_selector = selector
                    best_item = items[0]

    return best_selector, best_item


# ----- Pagination detection -----

def detect_pagination(soup: BeautifulSoup, current_url: str) -> dict:
    """Detect how the press release listing paginates."""
    # Look for next-page links
    next_patterns = [
        soup.select_one("a.next"),
        soup.select_one("a[rel='next']"),
        soup.select_one(".pagination a.next"),
        soup.select_one("li.next a"),
        soup.select_one("a.pager-next"),
        soup.select_one(".pager__item--next a"),
    ]
    for el in next_patterns:
        if el:
            href = el.get("href", "")
            if "page=" in href or "Page=" in href:
                match = re.search(r"[Pp]age[=_](\d+)", href)
                param = "page"
                if "Page=" in href:
                    param = "Page"
                if "PageNum" in href:
                    param = "PageNum_rs"
                return {
                    "type": "query_param",
                    "param": param,
                    "starts_at": 1 if match and match.group(1) == "2" else int(match.group(1)) - 1 if match else 1,
                }
            if re.search(r"/page/\d+", href):
                return {"type": "path_segment", "pattern": "/page/{n}", "starts_at": 1}
            return {"type": "link_follow", "next_selector": "a.next" if el.name == "a" else "li.next a"}

    # Check for pagination container
    pager = soup.select_one(".pagination") or soup.select_one(".pager") or soup.select_one("nav[aria-label*='pagination' i]")
    if pager:
        links = pager.select("a[href]")
        for link in links:
            href = link.get("href", "")
            if "page" in href.lower():
                match = re.search(r"[Pp]age[=_]?(\d+)", href)
                if match:
                    return {"type": "query_param", "param": "page", "starts_at": 1}

    # Check for load-more button (JS-based pagination)
    load_more = soup.select_one("button.load-more") or soup.select_one("a.load-more") or soup.select_one("[data-load-more]")
    if load_more:
        return {"type": "load_more", "selector": "button.load-more"}

    return {"type": "unknown"}


# ----- Main recon per member -----

async def probe_member(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    member: dict,
    chamber: str,
) -> dict:
    """Probe one member's website for press-release section."""
    async with semaphore:
        base = member["website_url"].rstrip("/")
        member_id = _make_id(member["full_name"])

        result = {
            "senator_id" if chamber == "senate" else "member_id": member_id,
            "full_name": member["full_name"],
            "party": member["party"],
            "state": member["state"],
            "official_url": base,
            "press_release_url": None,
            "parser_family": None,
            "requires_js": False,
            "pagination": {"type": "unknown"},
            "selectors": {},
            "confidence": 0.0,
            "notes": "",
            "last_verified": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "recon_status": "pending",
        }
        if chamber == "house":
            result["district"] = member.get("district", "")

        # Try each URL pattern
        for path in PRESS_RELEASE_PATHS:
            url = base + path
            try:
                resp = await client.get(url, follow_redirects=True)
                await asyncio.sleep(0.3)  # politeness delay
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as e:
                result["notes"] += f"Timeout/error on {path}. "
                continue

            if resp.status_code != 200:
                continue

            html = resp.text
            soup = BeautifulSoup(html, "lxml")

            # Check if this looks like a press-release listing
            page_text = soup.get_text(" ", strip=True).lower()
            pr_signals = sum([
                "press release" in page_text,
                "news release" in page_text,
                "statement" in page_text,
                "newsroom" in page_text,
            ])

            # Also check if there are multiple date-like items
            body_text = soup.body.get_text(" ", strip=True) if soup.body else ""
            date_matches = re.findall(
                r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}",
                body_text,
            )

            if pr_signals == 0 and len(date_matches) < 3:
                continue

            # Found a candidate page
            result["press_release_url"] = str(resp.url)
            cms = detect_cms(html, soup)
            try:
                selectors = extract_selectors(soup, str(resp.url))
            except Exception:
                selectors = {"list_item": None, "title": None, "date": None, "detail_link": None}
                result["notes"] += "Selector extraction failed. "
            try:
                pagination = detect_pagination(soup, str(resp.url))
            except Exception:
                pagination = {"type": "unknown"}

            result["selectors"] = selectors
            result["pagination"] = pagination
            result["requires_js"] = cms == "js-spa"
            result["parser_family"] = classify_parser_family(cms, selectors, str(resp.url))

            # Confidence scoring
            confidence = 0.3  # base for finding a page
            if selectors.get("list_item"):
                confidence += 0.25
            if selectors.get("title"):
                confidence += 0.15
            if selectors.get("date"):
                confidence += 0.1
            if selectors.get("detail_link"):
                confidence += 0.1
            if pagination["type"] != "unknown":
                confidence += 0.1
            if len(date_matches) >= 5:
                confidence += 0.05

            result["confidence"] = round(min(confidence, 1.0), 2)
            result["recon_status"] = "discovered"

            # Count items found on the listing page
            if selectors.get("list_item"):
                items = soup.select(selectors["list_item"])
                result["notes"] += f"Found {len(items)} items on listing page. "

            break  # Stop on first match

        if result["press_release_url"] is None:
            result["recon_status"] = "not_found"
            result["notes"] += "No press-release section discovered via URL probing. "

        _log(member["full_name"], result["recon_status"], result["confidence"], result.get("press_release_url", ""))
        return result


def _make_id(full_name: str) -> str:
    """Convert 'Elizabeth Warren' to 'warren-elizabeth'."""
    # Strip suffixes and middle initials for the ID
    name = re.sub(r"\s+(Jr\.|Sr\.|III|II|IV)\s*$", "", full_name)
    name = re.sub(r"\s+[A-Z]\.\s+", " ", name)
    name = re.sub(r"\s+[A-Z]\.$", "", name)
    parts = name.strip().split()
    if len(parts) >= 2:
        last = parts[-1].lower()
        first = parts[0].lower()
        # Remove non-alpha
        last = re.sub(r"[^a-z]", "", last)
        first = re.sub(r"[^a-z]", "", first)
        return f"{last}-{first}"
    return re.sub(r"[^a-z]", "", full_name.lower())


def _log(name: str, status: str, confidence: float, url: str):
    status_icon = {"discovered": "+", "not_found": "!", "pending": "?"}
    icon = status_icon.get(status, "?")
    conf_str = f"{confidence:.0%}" if confidence else "---"
    print(f"  [{icon}] {name:<30} {status:<12} conf={conf_str}  {url}")


# ----- Report generation -----

def generate_report(results: list, chamber: str) -> str:
    """Generate a human-readable markdown report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total = len(results)
    discovered = [r for r in results if r["recon_status"] == "discovered"]
    not_found = [r for r in results if r["recon_status"] == "not_found"]
    high_conf = [r for r in discovered if r["confidence"] >= 0.7]
    mid_conf = [r for r in discovered if 0.4 <= r["confidence"] < 0.7]
    low_conf = [r for r in discovered if r["confidence"] < 0.4]

    # Parser family distribution
    families = {}
    for r in discovered:
        fam = r.get("parser_family", "unknown")
        families[fam] = families.get(fam, 0) + 1

    # Pagination types
    pag_types = {}
    for r in discovered:
        pt = r.get("pagination", {}).get("type", "unknown")
        pag_types[pt] = pag_types.get(pt, 0) + 1

    lines = [
        f"# {chamber.title()} Press Release Recon Report",
        f"",
        f"**Run date:** {now}",
        f"**Total members:** {total}",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Discovered | {len(discovered)} |",
        f"| Not found | {len(not_found)} |",
        f"| High confidence (>=0.7) | {len(high_conf)} |",
        f"| Medium confidence (0.4-0.7) | {len(mid_conf)} |",
        f"| Low confidence (<0.4) | {len(low_conf)} |",
        f"| Requires JS rendering | {sum(1 for r in results if r.get('requires_js'))} |",
        f"",
        f"## Parser Family Distribution",
        f"",
        f"| Family | Count |",
        f"|--------|-------|",
    ]
    for fam, count in sorted(families.items(), key=lambda x: -x[1]):
        lines.append(f"| {fam} | {count} |")

    lines += [
        f"",
        f"## Pagination Types",
        f"",
        f"| Type | Count |",
        f"|------|-------|",
    ]
    for pt, count in sorted(pag_types.items(), key=lambda x: -x[1]):
        lines.append(f"| {pt} | {count} |")

    if not_found:
        lines += [
            f"",
            f"## Members Needing Manual Review",
            f"",
            f"These members' press-release sections could not be auto-discovered.",
            f"They may need browser-based recon or manual URL entry.",
            f"",
        ]
        for r in not_found:
            id_key = "senator_id" if chamber == "senate" else "member_id"
            lines.append(f"- **{r['full_name']}** ({r['party']}-{r['state']}) -- {r['official_url']}")
            if r.get("notes"):
                lines.append(f"  Notes: {r['notes'].strip()}")

    if low_conf:
        lines += [
            f"",
            f"## Low Confidence Discoveries",
            f"",
            f"Found a candidate page but selectors are unreliable.",
            f"",
        ]
        for r in low_conf:
            lines.append(f"- **{r['full_name']}** ({r['party']}-{r['state']}) -- conf={r['confidence']:.0%}")
            lines.append(f"  URL: {r.get('press_release_url', 'N/A')}")
            if r.get("notes"):
                lines.append(f"  Notes: {r['notes'].strip()}")

    lines += [
        f"",
        f"## All Members (sorted by confidence)",
        f"",
        f"| Name | Party | State | Confidence | Family | PR URL |",
        f"|------|-------|-------|------------|--------|--------|",
    ]
    for r in sorted(results, key=lambda x: -x.get("confidence", 0)):
        pr_url = r.get("press_release_url", "N/A") or "N/A"
        # Truncate URL for table readability
        pr_short = pr_url if len(pr_url) < 60 else pr_url[:57] + "..."
        lines.append(
            f"| {r['full_name']} | {r['party']} | {r['state']} | "
            f"{r.get('confidence', 0):.0%} | {r.get('parser_family', 'N/A')} | {pr_short} |"
        )

    return "\n".join(lines) + "\n"


# ----- Main -----

async def run_recon(chamber: str):
    """Run recon for the given chamber."""
    if chamber == "senate":
        seed_file = SEEDS_DIR / "senators_raw.json"
    else:
        seed_file = SEEDS_DIR / "house_raw.json"

    if not seed_file.exists():
        print(f"Seed file not found: {seed_file}")
        sys.exit(1)

    with open(seed_file) as f:
        members = json.load(f)

    print(f"\n{'='*60}")
    print(f"  Capitol Releases Recon -- {chamber.upper()}")
    print(f"  {len(members)} members to probe")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    async with httpx.AsyncClient(
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
        },
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
        follow_redirects=True,
    ) as client:
        tasks = [
            probe_member(client, semaphore, m, chamber)
            for m in members
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions that slipped through
    clean_results = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"  [X] {members[i]['full_name']}: {type(r).__name__}: {r}")
            clean_results.append({
                "senator_id" if chamber == "senate" else "member_id": _make_id(members[i]["full_name"]),
                "full_name": members[i]["full_name"],
                "party": members[i]["party"],
                "state": members[i]["state"],
                "official_url": members[i]["website_url"],
                "press_release_url": None,
                "parser_family": None,
                "requires_js": False,
                "pagination": {"type": "unknown"},
                "selectors": {},
                "confidence": 0.0,
                "notes": f"Exception during recon: {type(r).__name__}: {r}",
                "last_verified": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "recon_status": "error",
            })
        else:
            clean_results.append(r)

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_seed = SEEDS_DIR / f"{chamber}.json"
    output_report = RESULTS_DIR / f"recon_{chamber}.md"

    with open(output_seed, "w") as f:
        json.dump({"members": clean_results, "generated_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)

    report = generate_report(clean_results, chamber)
    with open(output_report, "w") as f:
        f.write(report)

    # Summary stats
    discovered = sum(1 for r in clean_results if r.get("recon_status") == "discovered")
    not_found = sum(1 for r in clean_results if r.get("recon_status") == "not_found")
    errors = sum(1 for r in clean_results if r.get("recon_status") == "error")
    avg_conf = sum(r.get("confidence", 0) for r in clean_results) / max(len(clean_results), 1)

    print(f"\n{'='*60}")
    print(f"  RESULTS: {discovered} discovered, {not_found} not found, {errors} errors")
    print(f"  Average confidence: {avg_conf:.0%}")
    print(f"  Seed file: {output_seed}")
    print(f"  Report:    {output_report}")
    print(f"{'='*60}\n")


async def main():
    parser = argparse.ArgumentParser(description="Capitol Releases recon")
    parser.add_argument("--chamber", choices=["senate", "house", "both"], default="senate")
    args = parser.parse_args()

    if args.chamber == "both":
        await run_recon("senate")
        await run_recon("house")
    else:
        await run_recon(args.chamber)


if __name__ == "__main__":
    asyncio.run(main())
