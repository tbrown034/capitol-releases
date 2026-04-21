"""
Deep content-stream discovery — bulletproof pass 2.

First-pass recon (content_stream_recon.py) matches navigation anchors against
stream regexes. That misses:
  - WordPress custom post types exposed via wp-json but not in global nav
    (same trick that surfaced hidden `press_releases` in the WP-JSON rescue)
  - Content sections listed in sitemap.xml but hidden in mega-menu JS
  - Sidebar filter/category controls on the press-release page that don't
    appear in the header nav
  - JS-rendered dropdown items on `requires_js` senators

This script probes THREE authoritative signals for every senator:

  1. /wp-json/wp/v2/types         -> all registered custom post types
  2. /sitemap.xml (and variants)  -> full URL inventory, clustered by path
  3. press_release_url page       -> sidebar / filter / category links

Emits `content_stream_deep_results.json` and prints a delta report vs
first-pass.
"""

import asyncio
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

SEEDS = Path(__file__).resolve().parent.parent / "seeds" / "senate.json"
FIRST_PASS = Path(__file__).resolve().parent / "content_stream_results.json"
OUT = Path(__file__).resolve().parent / "content_stream_deep_results.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
TIMEOUT = 25.0
CONCURRENCY = 10

# WordPress types that are structural — ignore
WP_BUILTIN_TYPES = {
    "post", "page", "attachment", "nav_menu_item", "wp_block",
    "wp_template", "wp_template_part", "wp_navigation", "wp_global_styles",
    "wp_font_family", "wp_font_face",
    # Elementor / page builder internals
    "elementor_library", "e-landing-page", "e-floating-buttons",
    "sensei_message", "sensei_lesson",
    # Common non-content types on senate WP sites
    "jetpack-portfolio", "jp_pay_order", "jp_pay_product",
    "amp_validated_url",
    "revision", "customize_changeset", "oembed_cache",
    "user_request", "wp_navigation",
    "acf-field", "acf-field-group",
    # Members / offices
    "member", "office", "staff", "state",
    # Legislative / issue infrastructure
    "issue", "topic", "bill", "category", "tag",
}

# Map WP post-type slugs -> our content_type taxonomy
WP_TYPE_MAP = {
    "press_release": "press_release", "press_releases": "press_release",
    "op_ed": "op_ed", "op_eds": "op_ed", "opeds": "op_ed",
    "editorial": "op_ed", "editorials": "op_ed",
    "commentary": "commentary", "commentaries": "commentary",
    "column": "commentary", "columns": "commentary",
    "weekly_column": "blog", "weekly-column": "blog",
    "weekly_columns": "blog", "weekly-columns": "blog",
    "weekly_report": "blog", "weekly-report": "blog",
    "blog": "blog", "blog_post": "blog", "blog_posts": "blog",
    "diary": "blog",
    "floor_statement": "floor_statement", "floor_statements": "floor_statement",
    "floor_speech": "floor_statement", "floor_speeches": "floor_statement",
    "statement": "statement", "statements": "statement",
    "letter": "letter", "letters": "letter",
    "photo_release": "photo_release", "photo_releases": "photo_release",
    "speech": "speech", "speeches": "speech",
    "remarks": "speech",
    "video": "video", "videos": "video",
    "podcast": "podcast", "podcasts": "podcast",
    "newsletter": "newsletter", "newsletters": "newsletter",
}

# Sitemap URL path keyword -> content_type (for sitemap clustering)
SITEMAP_KEYWORDS = {
    "op-ed": "op_ed", "op_ed": "op_ed", "opeds": "op_ed", "op-eds": "op_ed",
    "opinion": "op_ed", "editorial": "op_ed",
    "weekly-column": "blog", "weekly_column": "blog",
    "weekly-columns": "blog", "weekly_columns": "blog",
    "weekly-report": "blog",
    "blog": "blog", "diary": "blog",
    "commentary": "commentary", "commentaries": "commentary",
    "/columns/": "commentary", "/column/": "commentary",
    "floor-statement": "floor_statement", "floor_statement": "floor_statement",
    "floor-speech": "floor_statement", "floor_speech": "floor_statement",
    "floor-remarks": "floor_statement",
    "letter": "letter", "letters": "letter",
    "photo-release": "photo_release",
    "podcast": "podcast",
}

# Exclude sitemap URLs that match "in the news" patterns
SITEMAP_EXCLUDE = re.compile(
    r"/in-the-news|/in_the_news|/in-the-media|/news-clips?|/news-clippings?"
    r"|/media-(?:coverage|mentions|hits|clips?)|/press-(?:coverage|clips?|mentions)",
    re.I,
)

SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/wp-sitemap.xml",
]


# ---------------------------------------------------------------------------
# WP-JSON custom post type probe
# ---------------------------------------------------------------------------
async def probe_wp_json(client: httpx.AsyncClient, base: str) -> list[dict]:
    """Return list of {slug, rest_base, name, mapped_type} for non-builtin types."""
    url = urljoin(base + "/", "wp-json/wp/v2/types")
    try:
        r = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
    except Exception:
        return []
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []

    findings = []
    if not isinstance(data, dict):
        return findings
    for slug, meta in data.items():
        if slug in WP_BUILTIN_TYPES:
            continue
        if not isinstance(meta, dict):
            continue
        # Some types are internal-only; only surface if it has a rest_base
        rest_base = meta.get("rest_base")
        name = meta.get("name") or slug
        if not rest_base:
            continue
        mapped = WP_TYPE_MAP.get(slug.lower())
        # Also try rest_base
        if not mapped and rest_base:
            mapped = WP_TYPE_MAP.get(rest_base.lower())
        findings.append({
            "slug": slug,
            "rest_base": rest_base,
            "name": name,
            "mapped_type": mapped,
            "endpoint": urljoin(base + "/", f"wp-json/wp/v2/{rest_base}"),
        })
    return findings


# ---------------------------------------------------------------------------
# Sitemap scan
# ---------------------------------------------------------------------------
def parse_sitemap_urls(xml_text: str) -> list[str]:
    """Extract <loc> values from any sitemap or sitemap index."""
    urls = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return urls
    # Any element named "loc" regardless of namespace
    for el in root.iter():
        if el.tag.endswith("}loc") or el.tag == "loc":
            if el.text:
                urls.append(el.text.strip())
    return urls


async def probe_sitemap(client: httpx.AsyncClient, base: str) -> dict:
    """Fetch sitemap(s), recursively expand any sitemap index, return URLs grouped by path prefix."""
    seen_sitemaps = set()
    queue: list[str] = []
    for p in SITEMAP_PATHS:
        queue.append(urljoin(base + "/", p.lstrip("/")))

    all_urls: list[str] = []
    while queue and len(seen_sitemaps) < 20:
        sm_url = queue.pop(0)
        if sm_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sm_url)
        try:
            r = await client.get(sm_url, timeout=TIMEOUT, follow_redirects=True)
        except Exception:
            continue
        if r.status_code != 200 or "xml" not in r.headers.get("content-type", "").lower():
            # Try anyway if it parses
            if "<urlset" not in r.text and "<sitemapindex" not in r.text:
                continue
        locs = parse_sitemap_urls(r.text)
        # Recurse into sitemap indexes
        for loc in locs:
            if loc.endswith(".xml") and loc not in seen_sitemaps:
                queue.append(loc)
            else:
                all_urls.append(loc)

    return {"urls": all_urls, "sitemaps_checked": sorted(seen_sitemaps)}


_IN_WINDOW_RE = re.compile(r"/(202[56])/")  # 2025 or 2026 in URL path


def _url_is_in_window(url: str) -> bool | None:
    """Return True if URL contains a 2025/2026 date, False if pre-2025, None if unknown.

    Senate CMSes commonly embed year in the URL path (/2024/03/...) which lets us
    cheaply filter sitemap URLs to the Jan 2025+ collection window without a
    detail-page fetch. URLs with no date pattern return None -- keep them.
    """
    if _IN_WINDOW_RE.search(url):
        return True
    pre_window = re.search(r"/20(0\d|1\d|2[0-4])/", url)
    if pre_window:
        return False
    return None


def cluster_sitemap_streams(urls: list[str], press_path: str) -> list[dict]:
    """Find path prefixes that look like content streams based on URL inventory.

    Returns counts split into 'in_window' (2025+), 'pre_window' (pre-2025),
    and 'undated'. This is the correction for the earlier all-time count that
    inflated the recon estimate ~10x: Grassley's /commentary/ has ~1,250 URLs
    lifetime but only ~50-150 in the Jan 2025+ window.
    """
    # Count URLs under each candidate section-path prefix
    # A "section" = the 1st or 2nd path component, e.g. /news/op-eds, /media/op-eds
    section_urls: dict[str, list[str]] = defaultdict(list)
    for u in urls:
        try:
            path = urlparse(u).path
        except Exception:
            continue
        if not path:
            continue
        if SITEMAP_EXCLUDE.search(path):
            continue
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            continue
        # Consider 2-level section prefixes: /parts[0]/parts[1]/
        section = "/" + "/".join(parts[:2]) + "/"
        section_urls[section].append(u)

    candidates = []
    for section, members in section_urls.items():
        if len(members) < 3:
            continue
        section_lc = section.lower()
        # Skip anything under the already-configured press path
        if press_path and section_lc.startswith(press_path.lower()):
            continue
        # Match against stream keywords
        for kw, ctype in SITEMAP_KEYWORDS.items():
            if kw in section_lc:
                in_window = [u for u in members if _url_is_in_window(u) is True]
                pre_window = [u for u in members if _url_is_in_window(u) is False]
                undated = [u for u in members if _url_is_in_window(u) is None]
                candidates.append({
                    "section": section,
                    "category": ctype,
                    "url_count": len(members),
                    "in_window_count": len(in_window),
                    "pre_window_count": len(pre_window),
                    "undated_count": len(undated),
                    "sample": (in_window or undated or members)[:3],
                })
                break

    # Dedupe by section -- prefer the candidate with more in-window URLs since
    # that's what actually matters for collection.
    by_section = {}
    for c in candidates:
        cur = by_section.get(c["section"])
        if not cur or cur["in_window_count"] < c["in_window_count"]:
            by_section[c["section"]] = c
    return sorted(by_section.values(), key=lambda x: (-x["in_window_count"], -x["url_count"]))


# ---------------------------------------------------------------------------
# Press-page sidebar / filter scan
# ---------------------------------------------------------------------------
SIDEBAR_SELECTORS = [
    "aside", ".sidebar", "#sidebar", ".widget-area",
    ".filters", ".filter", ".categories", ".category-filter",
    ".facets", ".facet-menu",
    "select[name*='category']", "select[name*='type']",
    ".search-filters", ".taxonomy-filter",
    # Common WP widget classes
    ".wp-block-categories", ".widget_categories",
]


def scan_sidebar(soup: BeautifulSoup, base_url: str, press_path: str) -> list[dict]:
    """Scan press-page sidebar/filter regions for category links."""
    from urllib.parse import urljoin as _u
    found = []
    seen = set()
    for sel in SIDEBAR_SELECTORS:
        for region in soup.select(sel):
            # Anchor links inside the region
            for a in region.find_all("a", href=True):
                text = re.sub(r"\s+", " ", a.get_text()).strip()
                href = (a.get("href") or "").strip()
                if not text or not href or href.startswith("#"):
                    continue
                if len(text) > 40:
                    continue
                abs_href = _u(base_url, href)
                key = abs_href.split("#")[0].rstrip("/").lower()
                if key in seen:
                    continue
                seen.add(key)
                if SITEMAP_EXCLUDE.search(key):
                    continue
                # Skip under current press path
                if press_path and urlparse(abs_href).path.lower().startswith(press_path.lower()):
                    if urlparse(abs_href).path.rstrip("/") != press_path.rstrip("/"):
                        continue
                haystack = f"{text} | {abs_href.lower()}"
                for kw, ctype in SITEMAP_KEYWORDS.items():
                    if kw in haystack:
                        found.append({
                            "label": text,
                            "href": abs_href,
                            "category": ctype,
                            "source": "sidebar",
                        })
                        break

            # Option values in <select> filters
            for sel_el in region.select("option[value]"):
                val = sel_el.get("value", "").strip()
                label = re.sub(r"\s+", " ", sel_el.get_text()).strip()
                if not val or not label:
                    continue
                if len(label) > 40:
                    continue
                hay = f"{label} | {val}".lower()
                for kw, ctype in SITEMAP_KEYWORDS.items():
                    if kw in hay:
                        found.append({
                            "label": label,
                            "href": val if val.startswith("http") else _u(base_url, val),
                            "category": ctype,
                            "source": "filter-select",
                        })
                        break
    return found


# ---------------------------------------------------------------------------
# Per-senator
# ---------------------------------------------------------------------------
async def probe_one(client: httpx.AsyncClient, senator: dict, sem: asyncio.Semaphore) -> dict:
    sid = senator["senator_id"]
    official = (senator.get("official_url") or "").rstrip("/")
    press = senator.get("press_release_url", "")
    press_path = urlparse(press).path.rstrip("/") + "/" if press else ""

    result = {
        "senator_id": sid,
        "full_name": senator.get("full_name"),
        "state": senator.get("state"),
        "party": senator.get("party"),
        "official_url": official,
        "press_release_url": press,
        "wp_json_types": [],
        "sitemap_streams": [],
        "sitemap_checked": [],
        "sidebar_streams": [],
        "errors": [],
    }

    if not official:
        result["errors"].append("no official_url")
        return result

    async with sem:
        # 1) WP-JSON
        try:
            result["wp_json_types"] = await probe_wp_json(client, official)
        except Exception as e:
            result["errors"].append(f"wp-json: {type(e).__name__}: {e}")

        # 2) Sitemap
        try:
            sm = await probe_sitemap(client, official)
            result["sitemap_checked"] = sm["sitemaps_checked"]
            result["sitemap_streams"] = cluster_sitemap_streams(sm["urls"], press_path)
        except Exception as e:
            result["errors"].append(f"sitemap: {type(e).__name__}: {e}")

        # 3) Press-page sidebar
        if press:
            try:
                r = await client.get(press, timeout=TIMEOUT, follow_redirects=True)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "lxml")
                    result["sidebar_streams"] = scan_sidebar(soup, str(r.url), press_path)
            except Exception as e:
                result["errors"].append(f"sidebar: {type(e).__name__}: {e}")

    return result


async def main():
    seeds = json.loads(SEEDS.read_text())
    members = seeds["members"]
    sem = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        results = await asyncio.gather(*(probe_one(client, m, sem) for m in members))

    # Load first-pass to compute deltas
    first_pass = {}
    if FIRST_PASS.exists():
        fp = json.loads(FIRST_PASS.read_text())
        for r in fp["results"]:
            first_pass[r["senator_id"]] = r

    # Summary
    wp_hits = Counter()
    sitemap_hits = Counter()
    sidebar_hits = Counter()
    new_senators = []
    for r in results:
        sid = r["senator_id"]
        wp = [t for t in r["wp_json_types"] if t.get("mapped_type")]
        sm = r["sitemap_streams"]
        sb = r["sidebar_streams"]
        for t in wp:
            wp_hits[t["mapped_type"]] += 1
        for s in sm:
            sitemap_hits[s["category"]] += 1
        for s in sb:
            sidebar_hits[s["category"]] += 1

        fp = first_pass.get(sid, {})
        had_first = bool(fp.get("discovered"))
        has_new = bool(wp or sm or sb)
        if has_new and not had_first:
            new_senators.append(sid)

    summary = {
        "total_senators": len(results),
        "wp_json_findings_by_type": dict(wp_hits),
        "sitemap_findings_by_type": dict(sitemap_hits),
        "sidebar_findings_by_type": dict(sidebar_hits),
        "senators_with_new_deep_signals_not_in_first_pass": len(new_senators),
    }

    OUT.write_text(json.dumps({"summary": summary, "results": results}, indent=2))
    print(f"Wrote {OUT}")
    print(json.dumps(summary, indent=2))
    print()
    print("Senators with NEW signals vs first-pass:")
    for sid in sorted(new_senators):
        r = next(x for x in results if x["senator_id"] == sid)
        wp = [t["mapped_type"] for t in r["wp_json_types"] if t.get("mapped_type")]
        sm = [s["category"] for s in r["sitemap_streams"]]
        sb = [s["category"] for s in r["sidebar_streams"]]
        print(f"  {sid:28s}  wp={wp}  sitemap={sm}  sidebar={sb}")


if __name__ == "__main__":
    asyncio.run(main())
