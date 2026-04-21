"""
Per-senator content-stream discovery.

For each senator in senate.json, fetch their official site and press-release
landing page, then scan navigation/menus for additional original-content
streams we may not be scraping: op-eds, blog, diary, commentary, columns,
floor statements, speeches, letters.

Explicitly excludes "In the News" / "In the Media" / "News Clips" — those
surface curated external media mentions, which are out of scope per
CLAUDE.md ("Original content only").

Emits a per-senator report listing:
  - Configured press_release_url (baseline)
  - Additional streams discovered (url, label, category)
  - Any "in-the-news" streams skipped (so user can verify exclusion is right)

Does NOT modify senate.json — discovery only.
"""

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

SEEDS = Path(__file__).resolve().parent.parent / "seeds" / "senate.json"
OUT = Path(__file__).resolve().parent / "content_stream_results.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
TIMEOUT = 20.0
CONCURRENCY = 12

# (category, regex matched against link-text AND href path, case-insensitive)
INCLUDE = [
    ("op_ed",           re.compile(r"\bop[- ]?eds?\b|\beditorials?\b")),
    ("blog",            re.compile(r"\bblogs?\b|\bdiary\b|\bdiaries\b|\bweekly[- ]?(?:column|update|report)s?\b")),
    ("commentary",      re.compile(r"\bcommentary\b|\bcolumns?\b|\bperspectives?\b")),
    ("floor_statement", re.compile(r"\bfloor[- ]?(?:statements?|speeches|speech|remarks?)\b")),
    ("speech",          re.compile(r"^\s*speeches?\s*$|^\s*remarks?\s*$|\bpublic[- ]?speeches?\b")),
    ("letter",          re.compile(r"^\s*letters?\s*$|\boversight[- ]?letters?\b|\bpublic[- ]?letters?\b")),
    ("newsletter",      re.compile(r"\bnewsletters?\b|\be[- ]?newsletters?\b")),
    ("video",           re.compile(r"^\s*videos?\s*$")),
    ("podcast",         re.compile(r"\bpodcasts?\b")),
]

# Explicit opinion-form (feedback) pages — not content streams
OPINION_FORM = re.compile(
    r"\bshare[- ]?your[- ]?opinion\b"
    r"|\bcontact[- ]?(?:my[- ]?)?office\b"
    r"|/contact/|/share-your-opinion",
    re.I,
)

# Hard-exclude: external coverage / curated clippings
EXCLUDE = re.compile(
    r"\bin[- ]?the[- ]?(?:news|media)\b"
    r"|\bnews[- ]?clips?\b"
    r"|\bnews[- ]?clippings?\b"
    r"|\bmedia[- ]?(?:coverage|mentions|hits|clips?)\b"
    r"|\bpress[- ]?(?:coverage|clips?|mentions)\b"
    r"|\bICYMI\b"
    r"|\bfeatured[- ]?in\b"
    r"|\bnews[- ]?coverage\b",
    re.I,
)

# Junk we never want to classify as a content stream
STRUCTURAL_JUNK = re.compile(
    r"^(?:home|contact|about|biography|biograf|services?|help|issues?|legislation|"
    r"committee(?:s)?|constituent[- ]?services?|serving[- ]?you|visiting[- ]?washington|"
    r"schedule[- ]?(?:a[- ]?)?meeting|request|tour|flag|internship|jobs?|employment|"
    r"privacy|accessibility|rss|subscribe|sign[- ]?up|search|menu|skip[- ]?to|"
    r"academy[- ]?nominations?|grants?|veterans?|casework|photos?|gallery)\s*$",
    re.I,
)


def is_same_senate_domain(href: str, senator_host: str) -> bool:
    try:
        p = urlparse(href)
    except Exception:
        return False
    if not p.netloc:
        return True
    host = p.netloc.lower()
    return host.endswith(".senate.gov") and (senator_host.endswith(host) or host.endswith(senator_host))


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def find_streams(soup: BeautifulSoup, senator_host: str, base_url: str,
                 already_have: set[str], press_path_prefix: str):
    """Return (discovered, excluded) lists of {label, href, category}.

    press_path_prefix: the path portion of press_release_url. Any link whose
    path is under that prefix is treated as an individual article inside the
    already-configured stream, not a new stream.
    """
    discovered = []
    excluded = []
    seen_hrefs = set()

    # Favor nav/menu regions but fall back to all <a> if nav missing
    candidates = soup.select("nav a, header a, .menu a, #menu a, .navigation a, .nav a")
    if len(candidates) < 5:
        candidates = soup.find_all("a")

    for a in candidates:
        text = clean_text(a.get_text())
        href = (a.get("href") or "").strip()
        if not text or not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        # Stream labels are short section names ("Op-Eds", "Columns", "Blog").
        # Anything longer is an individual article title.
        if len(text) > 40:
            continue
        abs_href = urljoin(base_url, href)

        # Same-senator domain only
        if not is_same_senate_domain(abs_href, senator_host):
            continue

        # Normalize for dedup
        norm = abs_href.split("#")[0].rstrip("/").lower()
        if norm in seen_hrefs:
            continue
        seen_hrefs.add(norm)

        if norm in already_have:
            continue

        path = urlparse(abs_href).path.lower()
        haystack = f"{text} | {path}"

        # Exclude first
        if EXCLUDE.search(haystack):
            excluded.append({"label": text, "href": abs_href, "reason": "external-coverage pattern"})
            continue

        # Skip feedback forms (share-your-opinion, contact/my-office)
        if OPINION_FORM.search(haystack):
            continue

        # Skip individual articles inside the already-configured press stream
        # (e.g. /news/press-releases/cantwell-floor-speech-on-x is a release,
        # not a new stream — it lives under press_release_url's path prefix)
        if press_path_prefix and len(press_path_prefix) > 1 and path.startswith(press_path_prefix):
            if path != press_path_prefix and path.rstrip("/") != press_path_prefix.rstrip("/"):
                continue

        # Skip obvious structural junk (by text only — paths can be misleading)
        if STRUCTURAL_JUNK.match(text):
            continue

        for category, pat in INCLUDE:
            if pat.search(haystack):
                discovered.append({"label": text, "href": abs_href, "category": category})
                break

    return discovered, excluded


async def probe_senator(client: httpx.AsyncClient, senator: dict, sem: asyncio.Semaphore):
    sid = senator["senator_id"]
    official = senator.get("official_url", "")
    press = senator.get("press_release_url", "")
    if not official:
        return {"senator_id": sid, "error": "no official_url"}

    senator_host = urlparse(official).netloc.lower()
    already = {u.split("#")[0].rstrip("/").lower() for u in (official, press) if u}
    press_path = urlparse(press).path.lower().rstrip("/") + "/" if press else ""

    all_discovered: dict[str, dict] = {}
    all_excluded: dict[str, dict] = {}
    errors = []

    async with sem:
        for url in [official, press]:
            if not url:
                continue
            try:
                r = await client.get(url, follow_redirects=True, timeout=TIMEOUT)
            except Exception as e:
                errors.append(f"{url}: {type(e).__name__}")
                continue
            if r.status_code != 200:
                errors.append(f"{url}: HTTP {r.status_code}")
                continue
            soup = BeautifulSoup(r.text, "lxml")
            found, skipped = find_streams(soup, senator_host, str(r.url), already, press_path)
            for f in found:
                key = f["href"].split("#")[0].rstrip("/").lower()
                if key not in all_discovered:
                    all_discovered[key] = f
            for f in skipped:
                key = f["href"].split("#")[0].rstrip("/").lower()
                if key not in all_excluded:
                    all_excluded[key] = f

    return {
        "senator_id": sid,
        "full_name": senator.get("full_name"),
        "state": senator.get("state"),
        "party": senator.get("party"),
        "official_url": official,
        "press_release_url": press,
        "discovered": sorted(all_discovered.values(), key=lambda x: (x["category"], x["label"])),
        "excluded_in_the_news": sorted(all_excluded.values(), key=lambda x: x["label"]),
        "errors": errors,
    }


async def main():
    seeds = json.loads(SEEDS.read_text())
    members = seeds["members"]
    sem = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        results = await asyncio.gather(*(probe_senator(client, m, sem) for m in members))

    # Summary stats
    total = len(results)
    with_streams = sum(1 for r in results if r.get("discovered"))
    by_category: dict[str, int] = {}
    for r in results:
        for d in r.get("discovered", []):
            by_category[d["category"]] = by_category.get(d["category"], 0) + 1

    summary = {
        "total_senators": total,
        "senators_with_additional_streams": with_streams,
        "streams_by_category": dict(sorted(by_category.items(), key=lambda x: -x[1])),
    }

    OUT.write_text(json.dumps({"summary": summary, "results": results}, indent=2))
    print(f"Wrote {OUT}")
    print(f"Summary: {json.dumps(summary, indent=2)}")


if __name__ == "__main__":
    asyncio.run(main())
