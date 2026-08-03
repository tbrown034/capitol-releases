"""
RSS feed availability probe for all 437 US House members.

Forked from pipeline/recon/senate_rss_probe.py, with three House-specific
adjustments learned from house_comprehensive_probe_report.md (2026-04-24):

  1. Concurrency dropped from 12 to 3. The earlier comprehensive probe
     ran at 15 and AkamaiGHost returned 403 on 401/436 members (92%).
     Akamai's mitigation policy on *.house.gov is request-rate sensitive;
     keeping concurrency low and adding a politeness gap between probes
     against the same host is the cheapest way to stay under the floor
     without resorting to Playwright.
  2. URL pattern order leads with `/rss.xml`. The 28 members that
     penetrated the prior probe split 16 Drupal-with-/rss.xml + 10
     custom + 2 WordPress. House Drupal sites use /rss.xml; WordPress
     uses /feed/. Senate's pattern list led with /rss.xml + /feed/ in
     that order anyway, so we keep the order but add House-shaped
     paths (/news/rss, /media/press-releases.rss).
  3. Akamai-block detection. Any 403 with the AkamaiGHost server header
     or "Access Denied" body is logged as `akamai_blocked` so the report
     separates "site has no feed" from "we couldn't see the site at all".

Output:
    pipeline/recon/house_rss_probe.json
    pipeline/recon/house_rss_probe_report.md

Decision criteria for "swap-eligible" (RSS could power daily updates)
mirror the Senate probe so results are comparable across chambers:

    - Feed returns >= 10 items (House feeds cap at 10 per the prior
      probe; that is fine for daily-update use, only blocks backfill)
    - Dates parse cleanly on >= 90% of items
    - Most recent item is within the last 90 days
    - Title sample looks homogeneous (no newsletter/podcast pollution)
    - At least 2/3 sample item links return HTTP 200
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

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.lib.rss import parse_feed_items, _looks_like_feed  # noqa: E402

SEED_FILE = ROOT / "pipeline" / "seeds" / "house.json"
OUT_JSON = ROOT / "pipeline" / "recon" / "house_rss_probe.json"
OUT_REPORT = ROOT / "pipeline" / "recon" / "house_rss_probe_report.md"

# Concurrency 3 to stay under Akamai's rate floor on *.house.gov.
# At ~6 URL probes per member, 437 members, 0.15s politeness, this finishes
# in roughly 437 * 6 * 0.15 / 3 ~= 130s + per-request RTT. Plan ~5-8 min.
MAX_CONCURRENT = 3
REQUEST_TIMEOUT = 20.0

# Full Chrome 130 header set. Senate probe got away with bare Mozilla UA;
# House Akamai is more sensitive, so we ship the realistic browser fingerprint.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "application/rss+xml, application/atom+xml, application/xml;q=0.9, "
        "text/xml;q=0.8, text/html;q=0.7, */*;q=0.5"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not_A Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# House-first pattern order. /rss.xml comes first (Drupal 10 default on the
# shared *.house.gov platform); /feed/ second (WordPress members).
RSS_URL_PATTERNS = [
    "/rss.xml",
    "/feed/",
    "/feed",
    "/news/rss.xml",
    "/news/feed/",
    "/press-releases/feed/",
    "/media/press-releases.rss",
    "/media/press-releases/feed/",
    "/category/press-release/feed/",
    "/rss/feeds/?type=press",
]

BODY_THRESHOLD = 200
MIN_ITEMS = 10
MAX_STALENESS_DAYS = 90
MIN_DATED_FRACTION = 0.9


@dataclass
class FeedProbeRecord:
    url: str
    base_source: str
    status_code: int | None = None
    is_feed: bool = False
    feed_type: str = ""
    item_count: int = 0
    first_pub: str | None = None
    last_pub: str | None = None
    span_days: int | None = None
    sample_titles: list[str] = field(default_factory=list)
    body_looks_full: bool = False
    body_char_mean: int = 0
    dated_fraction: float = 0.0
    staleness_days: int | None = None
    sample_link_checks: list[dict] = field(default_factory=list)
    akamai_blocked: bool = False
    error: str = ""


@dataclass
class MemberProbeResult:
    member_id: str
    full_name: str
    state: str
    party: str
    district: str | int | None
    parser_family: str
    probes: list[FeedProbeRecord] = field(default_factory=list)
    best_feed_url: str | None = None
    best_probe_index: int | None = None
    swap_eligible: bool = False
    swap_reasoning: str = ""
    fully_blocked: bool = False  # every probe came back 403/Akamai


def _strip_html(html: str) -> str:
    if not html:
        return ""
    try:
        return BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)


def _is_akamai_block(resp: httpx.Response) -> bool:
    """Detect AkamaiGHost 403 page so we don't conflate it with 'no feed'."""
    if resp.status_code != 403:
        return False
    server = resp.headers.get("server", "").lower()
    if "akamaighost" in server:
        return True
    # Some Akamai responses omit the server header but ship an Access Denied body
    body_lower = (resp.text or "")[:500].lower()
    return "access denied" in body_lower and "reference" in body_lower


def _titles_look_homogeneous(titles: list[str]) -> tuple[bool, str]:
    if not titles:
        return False, "no titles"
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
    avg_len = sum(len(t) for t in titles) / max(len(titles), 1)
    if avg_len < 15:
        return False, f"titles too short (avg {avg_len:.0f} chars)"
    return True, "ok"


async def _check_link(client: httpx.AsyncClient, url: str) -> dict:
    out = {"url": url, "status": None, "error": ""}
    if not url:
        out["error"] = "empty url"
        return out
    try:
        resp = await client.head(url, follow_redirects=True, timeout=10.0)
        out["status"] = resp.status_code
        if resp.status_code in (405, 501):
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
        if _is_akamai_block(resp):
            rec.akamai_blocked = True
            return rec
        if resp.status_code != 200:
            return rec
        feed_type = _looks_like_feed(resp.headers.get("content-type", ""), resp.text)
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


async def _probe_member(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    member: dict,
) -> MemberProbeResult:
    async with sem:
        mid = member["member_id"]
        official = (member.get("official_url") or "").rstrip("/")
        press = (member.get("press_release_url") or "").rstrip("/")

        result = MemberProbeResult(
            member_id=mid,
            full_name=member.get("full_name", ""),
            state=member.get("state", ""),
            party=member.get("party", ""),
            district=member.get("district"),
            parser_family=member.get("parser_family", ""),
        )

        urls_to_probe: list[tuple[str, str]] = []
        if official:
            for p in RSS_URL_PATTERNS:
                urls_to_probe.append((official + p, "official_url"))
        if press and press != official:
            for p in RSS_URL_PATTERNS:
                urls_to_probe.append((press + p, "press_release_url"))

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
            await asyncio.sleep(0.15)

        # Akamai full-block detection: every probe returned akamai_blocked
        if result.probes and all(p.akamai_blocked for p in result.probes):
            result.fully_blocked = True

        feed_probes = [
            (i, p) for i, p in enumerate(result.probes) if p.is_feed and p.item_count > 0
        ]
        if feed_probes:
            feed_probes.sort(
                key=lambda ip: (ip[1].item_count, ip[1].span_days or 0),
                reverse=True,
            )
            best_i, best = feed_probes[0]
            result.best_feed_url = best.url
            result.best_probe_index = best_i

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
        elif result.fully_blocked:
            result.swap_reasoning = "all probes Akamai-blocked"
        else:
            result.swap_reasoning = "no working RSS feed found"

        elapsed = time.monotonic() - probe_start
        flag = "BLOCKED" if result.fully_blocked else ("Y" if result.swap_eligible else "N")
        print(
            f"  {mid:<32} fam={result.parser_family:<18} "
            f"feeds={len(feed_probes) if feed_probes else 0:>2} "
            f"swap={flag:<7} {result.swap_reasoning[:55]} ({elapsed:.1f}s)",
            flush=True,
        )
        return result


async def run():
    with open(SEED_FILE) as f:
        seed = json.load(f)
    members = seed["members"]
    print(f"Probing RSS for {len(members)} House members (concurrency={MAX_CONCURRENT})")

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    async with httpx.AsyncClient(
        headers=BROWSER_HEADERS,
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
        follow_redirects=True,
    ) as client:
        tasks = [_probe_member(client, sem, m) for m in members]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    clean: list[MemberProbeResult] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"  [X] {members[i]['member_id']}: {type(r).__name__}: {r}")
            clean.append(MemberProbeResult(
                member_id=members[i]["member_id"],
                full_name=members[i].get("full_name", ""),
                state=members[i].get("state", ""),
                party=members[i].get("party", ""),
                district=members[i].get("district"),
                parser_family=members[i].get("parser_family", ""),
                swap_reasoning=f"exception: {type(r).__name__}: {r}",
            ))
        else:
            clean.append(r)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "probe_url_patterns": RSS_URL_PATTERNS,
                "concurrency": MAX_CONCURRENT,
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

    report = generate_report(clean)
    with open(OUT_REPORT, "w") as f:
        f.write(report)

    print()
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_REPORT}")


def generate_report(results: list[MemberProbeResult]) -> str:
    total = len(results)
    fully_blocked = [r for r in results if r.fully_blocked]
    any_working = [r for r in results if r.best_feed_url]
    swap_eligible = [r for r in results if r.swap_eligible]
    unreliable = [r for r in results if r.best_feed_url and not r.swap_eligible]
    no_feed = [
        r for r in results
        if not r.best_feed_url and not r.fully_blocked
    ]

    def bm(r: MemberProbeResult) -> FeedProbeRecord | None:
        return r.probes[r.best_probe_index] if r.best_probe_index is not None else None

    family_counts = Counter(r.parser_family for r in results)
    family_eligible = Counter(r.parser_family for r in swap_eligible)
    family_blocked = Counter(r.parser_family for r in fully_blocked)

    lines: list[str] = []
    lines.append("# House RSS Probe Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Members probed:** {total}")
    lines.append(f"**Concurrency:** {MAX_CONCURRENT}")
    lines.append("")
    lines.append("## Topline")
    lines.append("")
    lines.append(f"- Any working RSS feed found: **{len(any_working)} / {total}**")
    lines.append(f"- Swap-eligible (good enough for daily updates): **{len(swap_eligible)} / {total}**")
    lines.append(f"- Unreliable RSS (feed exists but fails one or more criteria): **{len(unreliable)}**")
    lines.append(f"- Fully blocked (every probe Akamai 403): **{len(fully_blocked)}**")
    lines.append(f"- No RSS feed found (and not blocked): **{len(no_feed)}**")
    lines.append("")
    lines.append("## Breakdown by Parser Family")
    lines.append("")
    lines.append("| Family | Total | Swap-eligible | Akamai-blocked |")
    lines.append("|--------|-------|---------------|----------------|")
    for fam in sorted(family_counts.keys()):
        lines.append(
            f"| {fam} | {family_counts[fam]} | "
            f"{family_eligible.get(fam, 0)} | {family_blocked.get(fam, 0)} |"
        )
    lines.append("")

    lines.append("## Swap-Eligible Members (could move to RSS for daily updates)")
    lines.append("")
    lines.append(
        f"Criteria met: >={MIN_ITEMS} items, >={int(MIN_DATED_FRACTION*100)}% "
        f"of items have parseable dates, most recent item within "
        f"{MAX_STALENESS_DAYS} days, homogeneous titles, 2/3+ sample "
        f"links returning 200."
    )
    lines.append("")
    lines.append("| Member | State | District | Family | Feed URL | Items | Fresh (d) | Body? |")
    lines.append("|--------|-------|----------|--------|----------|-------|-----------|-------|")
    for r in sorted(swap_eligible, key=lambda x: (x.state, str(x.district), x.member_id)):
        best = bm(r)
        if not best:
            continue
        body_flag = "yes" if best.body_looks_full else f"teaser ({best.body_char_mean}c)"
        lines.append(
            f"| {r.full_name} | {r.state} | {r.district} | {r.parser_family} | "
            f"{best.url} | {best.item_count} | {best.staleness_days} | {body_flag} |"
        )
    lines.append("")

    lines.append("## Unreliable RSS (feed found but fails criteria — keep for later wave)")
    lines.append("")
    lines.append("| Member | State | Family | Feed URL | Items | Fresh (d) | Reason |")
    lines.append("|--------|-------|--------|----------|-------|-----------|--------|")
    for r in sorted(unreliable, key=lambda x: x.member_id):
        best = bm(r)
        if not best:
            continue
        fresh = best.staleness_days if best.staleness_days is not None else "n/a"
        lines.append(
            f"| {r.full_name} | {r.state} | {r.parser_family} | "
            f"{best.url} | {best.item_count} | {fresh} | {r.swap_reasoning} |"
        )
    lines.append("")

    lines.append("## Akamai-Blocked Members")
    lines.append("")
    lines.append(
        "Every probe URL returned 403 with AkamaiGHost server header or "
        "Access Denied body. These need a different transport (Playwright "
        "or curl_cffi with browser-TLS impersonation) before we can tell "
        "whether they have a working feed."
    )
    lines.append("")
    if fully_blocked:
        lines.append("| Member | State | District | Family |")
        lines.append("|--------|-------|----------|--------|")
        for r in sorted(fully_blocked, key=lambda x: (x.state, str(x.district), x.member_id)):
            lines.append(
                f"| {r.full_name} | {r.state} | {r.district} | {r.parser_family} |"
            )
    else:
        lines.append("_None — concurrency-3 + Chrome headers got past the policy._")
    lines.append("")

    lines.append("## No RSS Feed Found (probes returned 404/non-feed, not blocked)")
    lines.append("")
    lines.append("| Member | State | District | Family |")
    lines.append("|--------|-------|----------|--------|")
    for r in sorted(no_feed, key=lambda x: x.member_id):
        lines.append(
            f"| {r.full_name} | {r.state} | {r.district} | {r.parser_family} |"
        )
    lines.append("")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    asyncio.run(run())
