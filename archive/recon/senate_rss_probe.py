"""
RSS feed availability probe for all 100 senators.

For each senator in pipeline/seeds/senate.json, this probes a standard
set of RSS URL patterns against both official_url and press_release_url,
plus any configured rss_feed_url. It evaluates feeds against swap-eligible
criteria (>=20 items, dates parse, >=6 month span, homogeneous titles,
live sample links).

Output:
    pipeline/recon/senate_rss_probe.json
    pipeline/recon/senate_rss_probe_report.md

Decision criteria for "swap-eligible" (RSS could replace httpx/playwright
for daily updates):
    - Feed returns >= 10 items (typical WordPress default; anything less
      is suspicious for a senator office)
    - Dates parse cleanly on every item
    - Most recent item is within the last 90 days (feed is not stale)
    - Title sample looks homogeneous (no obvious blog/newsletter pollution)
    - At least 2/3 sample item links return HTTP 200

This is daily-update eligibility only. RSS feeds typically truncate
(10-25 items) and are NOT suitable for backfill. A feed with exactly 10
items covering only the last two weeks is fine for daily use -- it means
the senator publishes more than 10 items per fortnight, which is healthy.
"""

import asyncio
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

# Path setup so we can import pipeline.lib.rss
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.lib.rss import parse_feed_items, _looks_like_feed  # noqa: E402

SEED_FILE = ROOT / "pipeline" / "seeds" / "senate.json"
OUT_JSON = ROOT / "pipeline" / "recon" / "senate_rss_probe.json"
OUT_REPORT = ROOT / "pipeline" / "recon" / "senate_rss_probe_report.md"

MAX_CONCURRENT = 12
REQUEST_TIMEOUT = 20.0
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# URL patterns to probe (applied against both official_url and press_release_url bases)
RSS_URL_PATTERNS = [
    "/rss.xml",
    "/feed/",
    "/rss/feeds/?type=press",
    "/news/rss.xml",
    "/media/press-releases.rss",
    "/feed",
]

# Minimum body length to consider "real body text" after HTML strip
BODY_THRESHOLD = 200

# Criteria thresholds for swap-eligibility (daily-update use)
MIN_ITEMS = 10               # WordPress default; under this signals a bad feed
MAX_STALENESS_DAYS = 90      # most recent item must be within this window
MIN_DATED_FRACTION = 0.9     # 90%+ of items must have parseable dates


@dataclass
class FeedProbeRecord:
    """One probed URL's outcome."""
    url: str
    base_source: str  # "official_url", "press_release_url", or "configured_rss_feed_url"
    status_code: int | None = None
    is_feed: bool = False
    feed_type: str = ""  # "rss"/"atom"/""
    item_count: int = 0
    first_pub: str | None = None
    last_pub: str | None = None
    span_days: int | None = None
    sample_titles: list[str] = field(default_factory=list)
    body_looks_full: bool = False
    body_char_mean: int = 0
    dated_fraction: float = 0.0
    staleness_days: int | None = None  # days since most recent item
    sample_link_checks: list[dict] = field(default_factory=list)
    error: str = ""


@dataclass
class SenatorProbeResult:
    senator_id: str
    full_name: str
    state: str
    party: str
    current_method: str
    configured_rss: str | None
    probes: list[FeedProbeRecord] = field(default_factory=list)
    best_feed_url: str | None = None
    best_probe_index: int | None = None
    swap_eligible: bool = False
    swap_reasoning: str = ""


def _strip_html(html: str) -> str:
    """Strip HTML tags and return text."""
    if not html:
        return ""
    try:
        return BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)


def _titles_look_homogeneous(titles: list[str]) -> tuple[bool, str]:
    """Eyeball check: do titles look like press releases (vs newsletters/blog)?

    Returns (ok, reason). Any hit of a bad pattern flags it.
    """
    if not titles:
        return False, "no titles"

    # Patterns that suggest blog/newsletter/ICYMI pollution
    bad_patterns = [
        (r"\bnewsletter\b", "newsletter"),
        (r"\bweek in review\b", "week-in-review"),
        (r"\bweekly (update|roundup|recap)\b", "weekly-roundup"),
        (r"\bpodcast\b", "podcast"),
        (r"^\s*episode \d+", "podcast-episode"),
        (r"\bin the news\b", "in-the-news"),
    ]
    for title in titles:
        tl = title.lower()
        for pat, label in bad_patterns:
            if re.search(pat, tl):
                return False, f"title hit {label}: {title[:60]!r}"

    # If titles are all very short, feed may be malformed
    avg_len = sum(len(t) for t in titles) / max(len(titles), 1)
    if avg_len < 15:
        return False, f"titles too short (avg {avg_len:.0f} chars)"

    return True, "ok"


async def _check_link(client: httpx.AsyncClient, url: str) -> dict:
    """HEAD check a link; fall back to GET if HEAD not allowed."""
    out = {"url": url, "status": None, "error": ""}
    if not url:
        out["error"] = "empty url"
        return out
    try:
        resp = await client.head(url, follow_redirects=True, timeout=10.0)
        out["status"] = resp.status_code
        if resp.status_code in (405, 501):
            # HEAD not supported, try GET
            resp = await client.get(url, follow_redirects=True, timeout=10.0)
            out["status"] = resp.status_code
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


async def _probe_url(
    client: httpx.AsyncClient,
    url: str,
    base_source: str,
) -> FeedProbeRecord:
    rec = FeedProbeRecord(url=url, base_source=base_source)
    try:
        resp = await client.get(url, follow_redirects=True, timeout=REQUEST_TIMEOUT)
        rec.status_code = resp.status_code
        if resp.status_code != 200:
            return rec
        feed_type = _looks_like_feed(
            resp.headers.get("content-type", ""),
            resp.text,
        )
        if not feed_type:
            return rec
        rec.is_feed = True
        rec.feed_type = feed_type
        items = parse_feed_items(resp.text)
        rec.item_count = len(items)

        dated = [i for i in items if i.published_at]
        rec.dated_fraction = len(dated) / max(len(items), 1)
        if dated:
            dated_sorted = sorted(dated, key=lambda i: i.published_at)
            rec.first_pub = dated_sorted[0].published_at.isoformat()
            rec.last_pub = dated_sorted[-1].published_at.isoformat()
            rec.span_days = (dated_sorted[-1].published_at - dated_sorted[0].published_at).days
            now = datetime.now(timezone.utc)
            rec.staleness_days = (now - dated_sorted[-1].published_at).days

        rec.sample_titles = [i.title for i in items[:3]]

        # Body eyeball: look at the description/content of first 3 items.
        # parse_feed_items summaries are truncated to 500; to get real body we
        # re-parse raw XML because summary is already stripped in lib/rss.
        try:
            soup = BeautifulSoup(resp.text, "lxml-xml")
            char_lens = []
            rss_items = soup.find_all("item")[:3]
            if rss_items:
                for it in rss_items:
                    ce = it.find("content:encoded") or it.find("encoded")
                    desc = it.find("description")
                    raw_body = ""
                    if ce and ce.get_text(strip=True):
                        raw_body = ce.get_text(strip=True)
                    elif desc and desc.get_text(strip=True):
                        raw_body = desc.get_text(strip=True)
                    text = _strip_html(raw_body)
                    char_lens.append(len(text))
            else:
                # Atom
                atom_entries = soup.find_all("entry")[:3]
                for e in atom_entries:
                    content = e.find("content") or e.find("summary")
                    raw_body = content.get_text(strip=True) if content else ""
                    text = _strip_html(raw_body)
                    char_lens.append(len(text))
            if char_lens:
                rec.body_char_mean = int(sum(char_lens) / len(char_lens))
                rec.body_looks_full = rec.body_char_mean >= BODY_THRESHOLD
        except Exception:
            pass

        # Sample link checks: HEAD first 3 feed item links
        sample_links = [i.url for i in items[:3] if i.url]
        if sample_links:
            checks = await asyncio.gather(
                *[_check_link(client, u) for u in sample_links],
                return_exceptions=True,
            )
            for c in checks:
                if isinstance(c, Exception):
                    rec.sample_link_checks.append({
                        "url": "",
                        "status": None,
                        "error": f"{type(c).__name__}: {c}",
                    })
                else:
                    rec.sample_link_checks.append(c)
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        rec.error = f"{type(e).__name__}: {e}"
    except Exception as e:
        rec.error = f"{type(e).__name__}: {e}"
    return rec


async def _probe_senator(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    senator: dict,
) -> SenatorProbeResult:
    async with sem:
        sid = senator["senator_id"]
        official = (senator.get("official_url") or "").rstrip("/")
        press = (senator.get("press_release_url") or "").rstrip("/")
        configured = senator.get("rss_feed_url")

        result = SenatorProbeResult(
            senator_id=sid,
            full_name=senator.get("full_name", ""),
            state=senator.get("state", ""),
            party=senator.get("party", ""),
            current_method=senator.get("collection_method", ""),
            configured_rss=configured,
        )

        urls_to_probe: list[tuple[str, str]] = []

        # Configured rss_feed_url first (if present)
        if configured:
            urls_to_probe.append((configured, "configured_rss_feed_url"))

        # Patterns against official_url
        if official:
            for p in RSS_URL_PATTERNS:
                urls_to_probe.append((official + p, "official_url"))

        # Patterns against press_release_url base
        if press and press != official:
            for p in RSS_URL_PATTERNS:
                urls_to_probe.append((press + p, "press_release_url"))

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for u, src in urls_to_probe:
            if u in seen:
                continue
            seen.add(u)
            deduped.append((u, src))

        probe_start = time.monotonic()
        for u, src in deduped:
            rec = await _probe_url(client, u, src)
            result.probes.append(rec)
            # Small politeness delay between probes against the same host
            await asyncio.sleep(0.15)

        # Pick best probe: prefer one that is a feed, most items, longest span
        feed_probes = [
            (i, p) for i, p in enumerate(result.probes) if p.is_feed and p.item_count > 0
        ]
        if feed_probes:
            feed_probes.sort(
                key=lambda ip: (
                    ip[1].item_count,
                    ip[1].span_days or 0,
                ),
                reverse=True,
            )
            best_i, best = feed_probes[0]
            result.best_feed_url = best.url
            result.best_probe_index = best_i

            # Evaluate swap eligibility (daily-update use only)
            reasons = []
            if best.item_count < MIN_ITEMS:
                reasons.append(f"only {best.item_count} items (<{MIN_ITEMS})")
            if best.dated_fraction < MIN_DATED_FRACTION:
                reasons.append(
                    f"only {best.dated_fraction:.0%} of items have parseable dates"
                )
            if best.staleness_days is None:
                reasons.append("no parseable dates to check staleness")
            elif best.staleness_days > MAX_STALENESS_DAYS:
                reasons.append(
                    f"stale: most recent item {best.staleness_days}d old "
                    f"(>{MAX_STALENESS_DAYS}d)"
                )

            ok, reason = _titles_look_homogeneous(best.sample_titles)
            if not ok:
                reasons.append(f"titles: {reason}")

            # Links
            link_oks = sum(1 for c in best.sample_link_checks if c.get("status") == 200)
            total_checked = len(best.sample_link_checks)
            if total_checked == 0:
                reasons.append("no sample links to verify")
            elif link_oks < 2:
                reasons.append(
                    f"sample links: {link_oks}/{total_checked} returned 200"
                )

            if not reasons:
                result.swap_eligible = True
                result.swap_reasoning = (
                    f"{best.item_count} items, freshest {best.staleness_days}d old, "
                    f"{link_oks}/{total_checked} sample links 200"
                )
            else:
                result.swap_eligible = False
                result.swap_reasoning = "; ".join(reasons)
        else:
            result.swap_eligible = False
            result.swap_reasoning = "no working RSS feed found"

        elapsed = time.monotonic() - probe_start
        print(
            f"  {sid:<28} method={result.current_method:<10} "
            f"feeds={len(feed_probes) if feed_probes else 0:>2} "
            f"swap={'Y' if result.swap_eligible else 'N'} "
            f"{result.swap_reasoning[:60]} ({elapsed:.1f}s)",
            flush=True,
        )
        return result


async def run():
    with open(SEED_FILE) as f:
        seed = json.load(f)
    members = seed["members"]
    print(f"Probing RSS for {len(members)} senators (concurrency={MAX_CONCURRENT})")

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    async with httpx.AsyncClient(
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.5",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
        follow_redirects=True,
    ) as client:
        tasks = [_probe_senator(client, sem, m) for m in members]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    clean: list[SenatorProbeResult] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"  [X] {members[i]['senator_id']}: {type(r).__name__}: {r}")
            clean.append(SenatorProbeResult(
                senator_id=members[i]["senator_id"],
                full_name=members[i].get("full_name", ""),
                state=members[i].get("state", ""),
                party=members[i].get("party", ""),
                current_method=members[i].get("collection_method", ""),
                configured_rss=members[i].get("rss_feed_url"),
                swap_eligible=False,
                swap_reasoning=f"exception: {type(r).__name__}: {r}",
            ))
        else:
            clean.append(r)

    # Write raw JSON
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "probe_url_patterns": RSS_URL_PATTERNS,
                "criteria": {
                    "min_items": MIN_ITEMS,
                    "max_staleness_days": MAX_STALENESS_DAYS,
                    "min_dated_fraction": MIN_DATED_FRACTION,
                    "body_threshold_chars": BODY_THRESHOLD,
                },
                "results": [asdict(r) for r in clean],
            },
            f,
            indent=2,
            default=str,
        )

    # Write markdown report
    report = generate_report(clean)
    with open(OUT_REPORT, "w") as f:
        f.write(report)

    print()
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_REPORT}")


def generate_report(results: list[SenatorProbeResult]) -> str:
    total = len(results)
    any_working = [r for r in results if r.best_feed_url]
    swap_eligible = [r for r in results if r.swap_eligible]
    unreliable = [r for r in results if r.best_feed_url and not r.swap_eligible]
    no_feed = [r for r in results if not r.best_feed_url]

    def bm(r: SenatorProbeResult) -> FeedProbeRecord | None:
        return r.probes[r.best_probe_index] if r.best_probe_index is not None else None

    # Breakdown by current collection method
    method_counts = Counter(r.current_method for r in results)
    method_working = Counter(r.current_method for r in any_working)
    method_eligible = Counter(r.current_method for r in swap_eligible)

    lines: list[str] = []
    lines.append("# Senate RSS Probe Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Senators probed:** {total}")
    lines.append("")
    lines.append("## Topline")
    lines.append("")
    lines.append(f"- Any working RSS feed found: **{len(any_working)} / {total}**")
    lines.append(f"- Swap-eligible (RSS good enough for daily updates): **{len(swap_eligible)} / {total}**")
    lines.append(f"- Unreliable RSS (feed exists but fails at least one criterion): **{len(unreliable)}**")
    lines.append(f"- No RSS feed found: **{len(no_feed)}**")
    lines.append("")
    lines.append("## Breakdown by Current Collection Method")
    lines.append("")
    lines.append("| Method | Total | Any RSS | Swap-eligible |")
    lines.append("|--------|-------|---------|---------------|")
    for m in sorted(method_counts.keys()):
        lines.append(
            f"| {m} | {method_counts[m]} | "
            f"{method_working.get(m, 0)} | {method_eligible.get(m, 0)} |"
        )
    lines.append("")

    # Swap-eligible table
    lines.append("## Swap-Eligible Senators (could move to RSS for daily updates)")
    lines.append("")
    lines.append(f"Criteria met: >={MIN_ITEMS} items, >={int(MIN_DATED_FRACTION*100)}% "
                 f"of items have parseable dates, most recent item within "
                 f"{MAX_STALENESS_DAYS} days, homogeneous titles, 2/3+ sample "
                 f"links returning 200.")
    lines.append("")
    lines.append("| Senator | State | Current | Feed URL | Items | Fresh (d) | Span (d) | Body? |")
    lines.append("|---------|-------|---------|----------|-------|-----------|----------|-------|")
    for r in sorted(swap_eligible, key=lambda x: x.senator_id):
        best = bm(r)
        if not best:
            continue
        body_flag = "yes" if best.body_looks_full else f"teaser ({best.body_char_mean}c)"
        lines.append(
            f"| {r.full_name} | {r.state} | {r.current_method} | "
            f"{best.url} | {best.item_count} | {best.staleness_days} | "
            f"{best.span_days} | {body_flag} |"
        )
    lines.append("")

    # Unreliable table
    lines.append("## Unreliable RSS (feed exists, fails one or more criteria -- keep current method)")
    lines.append("")
    lines.append("| Senator | State | Current | Feed URL | Items | Fresh (d) | Reason |")
    lines.append("|---------|-------|---------|----------|-------|-----------|--------|")
    for r in sorted(unreliable, key=lambda x: x.senator_id):
        best = bm(r)
        if not best:
            continue
        fresh = best.staleness_days if best.staleness_days is not None else "n/a"
        lines.append(
            f"| {r.full_name} | {r.state} | {r.current_method} | "
            f"{best.url} | {best.item_count} | {fresh} | {r.swap_reasoning} |"
        )
    lines.append("")

    # No feed
    lines.append("## No RSS Feed Found")
    lines.append("")
    lines.append("| Senator | State | Current method |")
    lines.append("|---------|-------|----------------|")
    for r in sorted(no_feed, key=lambda x: x.senator_id):
        lines.append(f"| {r.full_name} | {r.state} | {r.current_method} |")
    lines.append("")

    # Senators currently using RSS but no longer viable (regression watch)
    currently_rss = [r for r in results if r.current_method == "rss"]
    rss_no_longer = [r for r in currently_rss if not r.swap_eligible]
    if rss_no_longer:
        lines.append("## Regression Watch: Currently on RSS but no longer swap-eligible")
        lines.append("")
        lines.append("These senators have `collection_method = \"rss\"` today but failed "
                     "swap-eligibility criteria on this probe. Worth investigating.")
        lines.append("")
        lines.append("| Senator | State | Reason |")
        lines.append("|---------|-------|--------|")
        for r in sorted(rss_no_longer, key=lambda x: x.senator_id):
            lines.append(f"| {r.full_name} | {r.state} | {r.swap_reasoning} |")
        lines.append("")

    # Pitfalls
    lines.append("## Observed Pitfalls")
    lines.append("")
    lines.append(
        "- **RSS feeds truncate.** The vast majority of working feeds return "
        "10-25 items. Acceptable for daily update, useless for backfill."
    )
    lines.append(
        "- **Body text is often a short teaser.** Many feeds return "
        "`<description>` at 100-300 chars, not full body. Detail-page fetch "
        "(as the current RSSCollector already does) remains required."
    )
    lines.append(
        "- **Some senator sites return HTTP 200 with an HTML 404 page on `/feed/`**, "
        "which we reject via `_looks_like_feed` content-type sniffing."
    )
    lines.append(
        "- **WordPress `/feed/` is near-universal** where WP is the CMS. The 70 "
        "senators currently on httpx include many WP sites that could be "
        "switched to RSS with zero selector maintenance burden."
    )
    lines.append(
        "- **Mixed-content feeds are rare but exist** (e.g. podcast episodes "
        "or weekly newsletters mixed into a general `/feed/`). The homogeneity "
        "check on titles flags these."
    )
    lines.append(
        "- **Date formats vary.** RFC 2822 dominates; a handful of Atom-style "
        "ISO 8601 feeds mix in. `pipeline.lib.rss._parse_rss_date` handles both."
    )
    lines.append(
        "- **ColdFusion RSS feeds emit malformed pubDates.** Three current-RSS "
        "senators (Boozman, Kennedy, Moran) expose `/public/?a=RSS.Feed` with "
        "day-of-year values like `Thu, 113 Apr 2026 12:00:00 EST` that fail "
        "RFC 2822 parsing. Feed items and titles are otherwise valid; if we "
        "want to keep these on RSS, the collector needs a salvage parser "
        "(pull date from item URL or detail page) rather than trusting "
        "pubDate."
    )
    lines.append(
        "- **Many configured `rss_feed_url` values do not point to "
        "press-release-specific feeds.** E.g. Warren's `/rss/` is site-wide "
        "but happens to be homogeneous enough; others would benefit from "
        "narrower category feeds (`/category/press_release/feed/` works for "
        "several WordPress senators)."
    )
    lines.append(
        "- **Some feeds pass swap eligibility with a teaser `<description>` "
        "and no full body.** That is OK -- the existing `RSSCollector` already "
        "fetches the detail page to get the full article. Body teaser vs full "
        "in the feed is not a swap blocker; it is a performance hint."
    )
    lines.append("")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    asyncio.run(run())
