"""
Unified reconnaissance probe for all 436 U.S. House member websites.

One async pass per member performs four probes against their official_url:

    A. Homepage fingerprint (1 GET)
       - HTTP status / final URL / response size
       - <meta name="generator"> content
       - CMS family detection (wordpress-evo, drupal-evo, wordpress, drupal,
         coldfusion, squarespace, custom, unknown)
       - Evo-theme shared-House-template signature
       - Page-builder hint (elementor, divi, wpbakery)
       - ColdFusion flag (.cfm links)
       - First candidate press-section link found in nav/footer

    B. RSS probe (up to 6 parallel GETs)
       - Patterns: /rss.xml, /feed/, /rss/feeds/?type=press,
         /news/rss.xml, /media/press-releases.rss, /feed
       - For each 200: feedparser parse, item count, date span, 3 titles,
         full-body heuristic (>200 chars after HTML strip)

    C. WordPress JSON probe (always runs: generator meta often missing)
       - /wp-json/wp/v2/posts?per_page=1
       - /wp-json/wp/v2/press_releases?per_page=1
       - /wp-json/wp/v2/pages?per_page=1
       - Records X-WP-Total header or array length, confirms title/content/date

    D. Candidate press-page probe (1 GET on first press-looking link from A)
       - Status, response size, naive list-item presence heuristic

Concurrency: 15. Request timeout 20s (connect 10s). Per-member cap 60s.
Retries once on ConnectError / TimeoutException; never on 4xx/5xx.

Emits incrementally to avoid losing work on interrupt:
    pipeline/recon/house_comprehensive_probe.json

Followed by:
    pipeline/recon/house_comprehensive_probe_report.md
"""

import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.lib.rss import parse_feed_items, _looks_like_feed  # noqa: E402

IN_PATH = ROOT / "pipeline" / "recon" / "house_members.json"
OUT_JSON = ROOT / "pipeline" / "recon" / "house_comprehensive_probe.json"
OUT_REPORT = ROOT / "pipeline" / "recon" / "house_comprehensive_probe_report.md"

CONCURRENCY = 15
REQUEST_TIMEOUT = 20.0
CONNECT_TIMEOUT = 10.0
PER_MEMBER_BUDGET_SECONDS = 60.0
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

RSS_URL_PATTERNS = [
    "/rss.xml",
    "/feed/",
    "/rss/feeds/?type=press",
    "/news/rss.xml",
    "/media/press-releases.rss",
    "/feed",
]

WP_ENDPOINTS = [
    ("posts", "/wp-json/wp/v2/posts?per_page=1"),
    ("press_releases", "/wp-json/wp/v2/press_releases?per_page=1"),
    ("pages", "/wp-json/wp/v2/pages?per_page=1"),
]

PRESS_LINK_RE = re.compile(r"/(press|news|media|newsroom|statements?|release)", re.I)

BODY_THRESHOLD = 200
LOG_EVERY = 25


# ---------- Data containers ----------


@dataclass
class HomepageResult:
    status: int | None = None
    final_url: str = ""
    bytes: int = 0
    generator: str | None = None
    cms_family: str = "unknown"
    wp_theme_hint: str | None = None
    evo_theme: bool = False
    coldfusion_signal: bool = False
    press_link_candidate: str | None = None


@dataclass
class RSSProbe:
    url: str
    status: int | None = None
    is_feed: bool = False
    item_count: int = 0
    date_span_days: int | None = None
    most_recent: str | None = None
    sample_titles: list[str] = field(default_factory=list)
    has_full_body: bool = False
    body_char_mean: int = 0


@dataclass
class RSSResult:
    probed: list[dict] = field(default_factory=list)
    best: dict | None = None


@dataclass
class WPJSONProbe:
    status: int | None = None
    total: int | None = None
    shape_ok: bool = False


@dataclass
class WPJSONResult:
    posts: dict | None = None
    press_releases: dict | None = None
    pages: dict | None = None


@dataclass
class PressPageResult:
    url: str = ""
    status: int | None = None
    bytes: int = 0
    likely_list: bool = False


@dataclass
class MemberResult:
    member_id: str
    official_url: str
    full_name: str = ""
    state: str = ""
    homepage: dict | None = None
    rss: dict | None = None
    wp_json: dict | None = None
    press_page: dict | None = None
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


# ---------- Helpers ----------


def _strip_html(html: str) -> str:
    if not html:
        return ""
    try:
        return BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)


def _detect_cms(html: str, generator: str | None, final_url: str) -> tuple[str, bool, str | None, bool]:
    """Return (cms_family, evo_theme, page_builder_hint, coldfusion_signal)."""
    lower = html.lower()
    evo = ("/wp-content/themes/evo/" in lower) or ("themes/evo/" in lower and "wp-content" in lower)
    page_builder = None
    if "elementor" in lower:
        page_builder = "elementor"
    elif re.search(r'\bet_pb_|class="et_pb_|/et-builder/|divi', lower):
        page_builder = "divi"
    elif "wpbakery" in lower or "js_composer" in lower or "vc_row" in lower:
        page_builder = "wpbakery"

    coldfusion = (".cfm" in lower) or ("coldfusion" in lower)

    gen = (generator or "").lower()
    is_wp = "wordpress" in gen or "/wp-content/" in lower or "/wp-includes/" in lower
    is_drupal = "drupal" in gen or "drupal-settings-json" in lower or "/sites/default/files/" in lower
    is_squarespace = "squarespace" in gen or "static1.squarespace.com" in lower
    is_coldfusion = coldfusion

    if is_wp and evo:
        family = "wordpress-evo"
    elif is_drupal and evo:
        family = "drupal-evo"
    elif is_wp:
        family = "wordpress"
    elif is_drupal:
        family = "drupal"
    elif is_coldfusion:
        family = "coldfusion"
    elif is_squarespace:
        family = "squarespace"
    elif evo:
        family = "evo-unknown-backend"
    else:
        # Signals absent — attempt structure-based fallback
        if "wp-json" in lower:
            family = "wordpress"
        else:
            family = "custom" if len(html) > 5000 else "unknown"

    return family, evo, page_builder, coldfusion


def _find_press_link(soup: BeautifulSoup, base_url: str, host: str) -> str | None:
    """Pick the first nav/footer link whose path looks press-ish."""
    candidates = soup.select(
        "nav a, header a, .menu a, #menu a, .navigation a, .nav a, footer a"
    )
    if len(candidates) < 5:
        candidates = soup.find_all("a")
    for a in candidates:
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        abs_href = urljoin(base_url, href)
        try:
            p = urlparse(abs_href)
        except Exception:
            continue
        # Same-host only (house.gov typically)
        if p.netloc and host and p.netloc.lower() != host.lower():
            continue
        if not p.path or p.path == "/":
            continue
        if PRESS_LINK_RE.search(p.path):
            return abs_href
    return None


async def _retry_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float = REQUEST_TIMEOUT,
) -> httpx.Response | None:
    """GET with a single retry on connect/timeout errors. Returns None on terminal failure."""
    try:
        return await client.get(url, follow_redirects=True, timeout=timeout)
    except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException, httpx.RemoteProtocolError):
        await asyncio.sleep(0.2)
        try:
            return await client.get(url, follow_redirects=True, timeout=timeout)
        except Exception:
            return None
    except Exception:
        return None


# ---------- Probes ----------


async def probe_homepage(
    client: httpx.AsyncClient, official_url: str
) -> tuple[HomepageResult, str, str]:
    """Returns (result, html, final_url_base)."""
    res = HomepageResult()
    resp = await _retry_get(client, official_url)
    if resp is None:
        return res, "", official_url
    res.status = resp.status_code
    res.final_url = str(resp.url)
    res.bytes = len(resp.content or b"")
    if resp.status_code != 200:
        return res, "", official_url
    html = resp.text
    soup = BeautifulSoup(html, "lxml")
    gen_tag = soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
    generator = gen_tag.get("content") if gen_tag else None
    res.generator = generator

    family, evo, page_builder, coldfusion = _detect_cms(html, generator, res.final_url)
    res.cms_family = family
    res.evo_theme = evo
    res.wp_theme_hint = page_builder
    res.coldfusion_signal = coldfusion

    host = urlparse(res.final_url).netloc
    res.press_link_candidate = _find_press_link(soup, res.final_url, host)

    return res, html, res.final_url


async def probe_rss_one(client: httpx.AsyncClient, url: str) -> RSSProbe:
    rec = RSSProbe(url=url)
    resp = await _retry_get(client, url)
    if resp is None:
        return rec
    rec.status = resp.status_code
    if resp.status_code != 200:
        return rec
    feed_type = _looks_like_feed(resp.headers.get("content-type", ""), resp.text)
    if not feed_type:
        return rec
    rec.is_feed = True
    items = parse_feed_items(resp.text)
    rec.item_count = len(items)
    dated = [i for i in items if i.published_at]
    if dated:
        dated.sort(key=lambda i: i.published_at)
        rec.date_span_days = (dated[-1].published_at - dated[0].published_at).days
        rec.most_recent = dated[-1].published_at.isoformat()
    rec.sample_titles = [i.title for i in items[:3] if i.title]

    # Body eyeball: inspect first three items' content/description
    try:
        soup = BeautifulSoup(resp.text, "lxml-xml")
        char_lens = []
        rss_items = soup.find_all("item")[:3]
        if rss_items:
            for it in rss_items:
                ce = it.find("content:encoded") or it.find("encoded")
                desc = it.find("description")
                raw = ""
                if ce and ce.get_text(strip=True):
                    raw = ce.get_text(strip=True)
                elif desc and desc.get_text(strip=True):
                    raw = desc.get_text(strip=True)
                char_lens.append(len(_strip_html(raw)))
        else:
            atom_entries = soup.find_all("entry")[:3]
            for e in atom_entries:
                content = e.find("content") or e.find("summary")
                raw = content.get_text(strip=True) if content else ""
                char_lens.append(len(_strip_html(raw)))
        if char_lens:
            rec.body_char_mean = int(sum(char_lens) / len(char_lens))
            rec.has_full_body = rec.body_char_mean >= BODY_THRESHOLD
    except Exception:
        pass

    return rec


async def probe_rss(client: httpx.AsyncClient, base_url: str) -> RSSResult:
    base = base_url.rstrip("/")
    urls = [base + p for p in RSS_URL_PATTERNS]
    # Dedup while preserving order
    seen = set()
    unique = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        unique.append(u)

    probes = await asyncio.gather(*(probe_rss_one(client, u) for u in unique))
    result = RSSResult()
    for p in probes:
        result.probed.append({"url": p.url, "status": p.status})

    # Pick best: feed + most items, tiebreak by span
    feeds = [p for p in probes if p.is_feed and p.item_count > 0]
    if feeds:
        feeds.sort(key=lambda p: (p.item_count, p.date_span_days or 0), reverse=True)
        best = feeds[0]
        result.best = {
            "url": best.url,
            "item_count": best.item_count,
            "date_span_days": best.date_span_days,
            "most_recent": best.most_recent,
            "sample_titles": best.sample_titles,
            "has_full_body": best.has_full_body,
            "body_char_mean": best.body_char_mean,
        }
    return result


async def probe_wp_endpoint(
    client: httpx.AsyncClient, url: str
) -> WPJSONProbe:
    rec = WPJSONProbe()
    resp = await _retry_get(client, url)
    if resp is None:
        return rec
    rec.status = resp.status_code
    if resp.status_code != 200:
        return rec
    total_hdr = resp.headers.get("X-WP-Total") or resp.headers.get("x-wp-total")
    try:
        total = int(total_hdr) if total_hdr else None
    except (TypeError, ValueError):
        total = None
    try:
        body = resp.json()
    except Exception:
        # Some WP sites wrap JSON in HTML debug noise; try to slice
        txt = resp.text
        lb = txt.find("[")
        rb = txt.rfind("]")
        if 0 <= lb < rb:
            try:
                body = json.loads(txt[lb : rb + 1])
            except Exception:
                return rec
        else:
            return rec
    if isinstance(body, list):
        if total is None:
            total = len(body)
        first = body[0] if body else None
        if first and isinstance(first, dict):
            shape_ok = (
                ("title" in first)
                and ("content" in first or "excerpt" in first)
                and ("date" in first or "date_gmt" in first)
            )
            rec.shape_ok = bool(shape_ok)
    rec.total = total
    return rec


async def probe_wp_json(client: httpx.AsyncClient, base_url: str) -> WPJSONResult:
    base = base_url.rstrip("/")
    results = await asyncio.gather(
        *(probe_wp_endpoint(client, base + path) for _, path in WP_ENDPOINTS)
    )
    out = WPJSONResult()
    for (name, _), rec in zip(WP_ENDPOINTS, results):
        payload = {"status": rec.status, "total": rec.total, "shape_ok": rec.shape_ok}
        setattr(out, name, payload)
    return out


async def probe_press_page(
    client: httpx.AsyncClient, url: str
) -> PressPageResult:
    rec = PressPageResult(url=url)
    resp = await _retry_get(client, url)
    if resp is None:
        return rec
    rec.status = resp.status_code
    rec.bytes = len(resp.content or b"")
    if resp.status_code == 200:
        html = resp.text
        soup = BeautifulSoup(html, "lxml")
        # Naive list-ish signal: 5+ article/li/h3 anchor structures
        article_count = len(soup.select("article"))
        li_anchor_count = len(soup.select("li a"))
        h_anchor_count = len(soup.select("h2 a, h3 a"))
        rec.likely_list = (
            article_count >= 3 or li_anchor_count >= 20 or h_anchor_count >= 5
        )
    return rec


# ---------- Per-member orchestration ----------


async def probe_member(
    client: httpx.AsyncClient,
    member: dict,
    sem: asyncio.Semaphore,
) -> MemberResult:
    mid = member["member_id"]
    official = (member.get("official_url") or "").strip()
    result = MemberResult(
        member_id=mid,
        official_url=official,
        full_name=member.get("full_name", ""),
        state=member.get("state", ""),
    )
    if not official:
        result.errors.append("no official_url")
        return result

    async with sem:
        start = time.monotonic()

        async def _do():
            homepage, html, final_url = await probe_homepage(client, official)
            result.homepage = asdict(homepage)

            base_for_probes = final_url or official

            rss_task = asyncio.create_task(probe_rss(client, base_for_probes))
            wp_task = asyncio.create_task(probe_wp_json(client, base_for_probes))
            if homepage.press_link_candidate:
                press_task = asyncio.create_task(
                    probe_press_page(client, homepage.press_link_candidate)
                )
            else:
                press_task = None

            rss_res = await rss_task
            wp_res = await wp_task
            press_res = await press_task if press_task else None

            result.rss = {"best": rss_res.best, "probed": rss_res.probed}
            result.wp_json = {
                "posts": wp_res.posts,
                "press_releases": wp_res.press_releases,
                "pages": wp_res.pages,
            }
            if press_res:
                result.press_page = asdict(press_res)

        try:
            await asyncio.wait_for(_do(), timeout=PER_MEMBER_BUDGET_SECONDS)
        except asyncio.TimeoutError:
            result.errors.append("per-member timeout >60s")
        except Exception as e:
            result.errors.append(f"{type(e).__name__}: {e}")

        result.elapsed_seconds = round(time.monotonic() - start, 2)

    return result


# ---------- Report generation ----------


def _classify_best_option(r: dict) -> str:
    """Pick the single best collection strategy for a member.

    Order of preference:
      1. rss (RSS feed with >=10 items and recent)
      2. wp_json (press_releases endpoint wins over posts)
      3. httpx (static HTML press page responded 200 w/ list signal)
      4. playwright (site responded but offers no static route)
      5. dead (no useful signal)
    """
    rss = (r.get("rss") or {}).get("best")
    if rss and rss.get("item_count", 0) >= 10:
        return "rss"

    wp = r.get("wp_json") or {}
    pr = wp.get("press_releases")
    posts = wp.get("posts")
    if pr and pr.get("status") == 200 and (pr.get("total") or 0) > 0 and pr.get("shape_ok"):
        return "wp_json"
    if posts and posts.get("status") == 200 and (posts.get("total") or 0) > 0 and posts.get("shape_ok"):
        return "wp_json"

    press = r.get("press_page")
    if press and press.get("status") == 200 and press.get("likely_list"):
        return "httpx"

    hp = r.get("homepage") or {}
    if hp.get("status") == 200:
        return "playwright"

    # If homepage failed or <200
    return "dead"


def _any_options(r: dict) -> set[str]:
    """All potential strategies that have at least partial signal."""
    opts: set[str] = set()
    rss = (r.get("rss") or {}).get("best")
    if rss and rss.get("item_count", 0) > 0:
        opts.add("rss")
    wp = r.get("wp_json") or {}
    for name in ("posts", "press_releases"):
        ep = wp.get(name)
        if ep and ep.get("status") == 200 and (ep.get("total") or 0) > 0:
            opts.add("wp_json")
    press = r.get("press_page")
    if press and press.get("status") == 200 and press.get("likely_list"):
        opts.add("httpx")
    hp = r.get("homepage") or {}
    if hp.get("status") == 200:
        opts.add("playwright")
    return opts


def _swap_eligible_rss(rss_best: dict | None) -> bool:
    if not rss_best:
        return False
    if rss_best.get("item_count", 0) < 20:
        return False
    span = rss_best.get("date_span_days") or 0
    if span < 180:
        return False
    if not rss_best.get("has_full_body"):
        return False
    titles = rss_best.get("sample_titles") or []
    if not titles:
        return False
    for t in titles:
        tl = (t or "").lower()
        for bad in ("newsletter", "week in review", "podcast", "in the news"):
            if bad in tl:
                return False
    avg_len = sum(len(t) for t in titles) / max(len(titles), 1)
    if avg_len < 15:
        return False
    return True


def generate_report(results: list[dict], wall_clock: float) -> str:
    total = len(results)
    # CMS families
    fam_counts: dict[str, int] = {}
    evo_count = 0
    for r in results:
        hp = r.get("homepage") or {}
        fam = hp.get("cms_family") or "unknown"
        fam_counts[fam] = fam_counts.get(fam, 0) + 1
        if hp.get("evo_theme"):
            evo_count += 1

    # Coverage matrix
    best_counts: dict[str, int] = {}
    any_counts: dict[str, int] = {
        "rss": 0,
        "wp_json": 0,
        "httpx": 0,
        "playwright": 0,
    }
    for r in results:
        best = _classify_best_option(r)
        best_counts[best] = best_counts.get(best, 0) + 1
        for k in _any_options(r):
            any_counts[k] = any_counts.get(k, 0) + 1

    # RSS quality cut
    with_any_rss = sum(
        1 for r in results if ((r.get("rss") or {}).get("best") or {}).get("item_count", 0) > 0
    )
    rss_swap_eligible = sum(
        1 for r in results if _swap_eligible_rss((r.get("rss") or {}).get("best"))
    )

    # WordPress JSON opportunity
    wp_posts_open = 0
    wp_press_open = 0
    wp_any_open = 0
    wp_press_examples: list[tuple[str, int]] = []
    for r in results:
        wp = r.get("wp_json") or {}
        p = wp.get("posts") or {}
        pr = wp.get("press_releases") or {}
        any_hit = False
        if p.get("status") == 200 and (p.get("total") or 0) > 0:
            wp_posts_open += 1
            any_hit = True
        if pr.get("status") == 200 and (pr.get("total") or 0) > 0:
            wp_press_open += 1
            any_hit = True
            wp_press_examples.append((r["member_id"], pr.get("total") or 0))
        if any_hit:
            wp_any_open += 1
    wp_press_examples.sort(key=lambda t: -t[1])

    # Problem list
    problems: list[tuple[str, str]] = []
    for r in results:
        hp = r.get("homepage") or {}
        status = hp.get("status")
        if r.get("errors"):
            problems.append((r["member_id"], f"errors: {'; '.join(r['errors'])}"))
            continue
        if status is None:
            problems.append((r["member_id"], "no response"))
        elif status >= 500:
            problems.append((r["member_id"], f"HTTP {status}"))
        elif status in (404, 410, 451):
            problems.append((r["member_id"], f"HTTP {status}"))
        else:
            # Redirected off-domain?
            try:
                original_host = urlparse(r["official_url"]).netloc.lower()
                final_host = urlparse(hp.get("final_url", "")).netloc.lower()
                if final_host and original_host and not final_host.endswith(".house.gov") and original_host.endswith(".house.gov"):
                    problems.append((r["member_id"], f"redirected off .house.gov to {final_host}"))
            except Exception:
                pass

    # Coverage projection (cumulative, member-unique)
    phase1 = set()  # RSS-best
    phase2 = set(phase1)  # + WP JSON
    phase3 = set(phase2)  # + shared-Evo parser (httpx-ready)
    phase4 = set(phase3)  # + playwright
    for r in results:
        opts = _any_options(r)
        if "rss" in opts and ((r.get("rss") or {}).get("best") or {}).get("item_count", 0) >= 10:
            phase1.add(r["member_id"])
    phase2 = set(phase1)
    for r in results:
        if "wp_json" in _any_options(r):
            phase2.add(r["member_id"])
    phase3 = set(phase2)
    for r in results:
        hp = r.get("homepage") or {}
        # Shared-Evo parser would cover any 200-returning Evo member
        if hp.get("evo_theme") and hp.get("status") == 200:
            phase3.add(r["member_id"])
        # Also include those with a responding press page
        press = r.get("press_page") or {}
        if press.get("status") == 200 and press.get("likely_list"):
            phase3.add(r["member_id"])
    phase4 = set(phase3)
    for r in results:
        hp = r.get("homepage") or {}
        if hp.get("status") == 200:
            phase4.add(r["member_id"])

    def pct(n: int) -> str:
        return f"{(100.0 * n / total):.1f}%"

    lines: list[str] = []
    lines.append("# House Comprehensive Probe Report")
    lines.append("")
    lines.append(
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    lines.append(f"**Members probed:** {total}")
    lines.append(f"**Wall-clock runtime:** {wall_clock:.1f}s")
    lines.append("")

    # Section a
    lines.append("## a. Coverage matrix")
    lines.append("")
    lines.append("Best-option (single strategy per member, in preference order):")
    lines.append("")
    lines.append("| Strategy | Members | % |")
    lines.append("|----------|---------|---|")
    for strat in ("rss", "wp_json", "httpx", "playwright", "dead"):
        n = best_counts.get(strat, 0)
        lines.append(f"| {strat} | {n} | {pct(n)} |")
    lines.append("")
    lines.append("Any-option (member may count in multiple rows):")
    lines.append("")
    lines.append("| Strategy | Members | % |")
    lines.append("|----------|---------|---|")
    for strat in ("rss", "wp_json", "httpx", "playwright"):
        n = any_counts.get(strat, 0)
        lines.append(f"| {strat} | {n} | {pct(n)} |")
    lines.append("")

    # Section b
    lines.append("## b. CMS family distribution")
    lines.append("")
    lines.append("| CMS family | Members | % |")
    lines.append("|------------|---------|---|")
    for fam, n in sorted(fam_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {fam} | {n} | {pct(n)} |")
    lines.append("")

    # Section c
    lines.append("## c. RSS quality cut")
    lines.append("")
    lines.append(
        f"- Members with any working RSS feed: **{with_any_rss} / {total}** ({pct(with_any_rss)})"
    )
    lines.append(
        f"- Swap-eligible (>=20 items, >=6-month span, full body, homogeneous titles): "
        f"**{rss_swap_eligible} / {total}** ({pct(rss_swap_eligible)})"
    )
    lines.append("")

    # Section d
    lines.append("## d. WordPress JSON opportunity")
    lines.append("")
    lines.append(
        f"- `/wp-json/wp/v2/posts` open with non-zero total: **{wp_posts_open}**"
    )
    lines.append(
        f"- `/wp-json/wp/v2/press_releases` open with non-zero total: **{wp_press_open}**"
    )
    lines.append(
        f"- Any WP JSON endpoint open: **{wp_any_open}** ({pct(wp_any_open)})"
    )
    lines.append("")
    if wp_press_examples:
        lines.append("Top 20 `press_releases` totals (quick-win candidates):")
        lines.append("")
        lines.append("| Member | X-WP-Total |")
        lines.append("|--------|------------|")
        for mid, t in wp_press_examples[:20]:
            lines.append(f"| {mid} | {t} |")
        lines.append("")

    # Section e
    lines.append("## e. Shared-template leverage")
    lines.append("")
    lines.append(
        f"- Members detected on the `/wp-content/themes/evo/` shared House template: "
        f"**{evo_count}** ({pct(evo_count)})"
    )
    lines.append(
        "- One well-written Evo parser could cover all of them with a single "
        "selector set. This is the highest-leverage single investment."
    )
    lines.append("")

    # Section f
    lines.append("## f. Problem list")
    lines.append("")
    if not problems:
        lines.append("- No members returned 5xx, timeout, or off-domain redirect.")
    else:
        lines.append(f"- Total problem members: **{len(problems)}**")
        lines.append("")
        lines.append("| Member | Issue |")
        lines.append("|--------|-------|")
        for mid, why in sorted(problems):
            lines.append(f"| {mid} | {why} |")
    lines.append("")

    # Section g
    lines.append("## g. Coverage projection")
    lines.append("")
    lines.append("Cumulative, member-unique:")
    lines.append("")
    lines.append("| Phase | Strategy added | Cumulative members | % of 436 |")
    lines.append("|-------|----------------|--------------------|---------:|")
    lines.append(
        f"| 1 | RSS only | {len(phase1)} | {pct(len(phase1))} |"
    )
    lines.append(
        f"| 2 | + WordPress JSON | {len(phase2)} | {pct(len(phase2))} |"
    )
    lines.append(
        f"| 3 | + shared-Evo / static press page | {len(phase3)} | {pct(len(phase3))} |"
    )
    lines.append(
        f"| 4 | + per-member Playwright | {len(phase4)} | {pct(len(phase4))} |"
    )
    lines.append("")

    return "\n".join(lines) + "\n"


# ---------- Main ----------


async def run():
    with open(IN_PATH) as f:
        seed = json.load(f)
    members = seed["members"]
    print(f"Probing {len(members)} House members (concurrency={CONCURRENCY})", flush=True)

    sem = asyncio.Semaphore(CONCURRENCY)
    timeout = httpx.Timeout(REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT)
    limits = httpx.Limits(
        max_connections=CONCURRENCY * 4,
        max_keepalive_connections=CONCURRENCY * 2,
    )

    # Incremental checkpoint state
    completed: list[dict] = []
    start_all = time.monotonic()

    async with httpx.AsyncClient(
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "application/rss+xml,application/json;q=0.8,*/*;q=0.5"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
    ) as client:
        tasks = [
            asyncio.create_task(probe_member(client, m, sem))
            for m in members
        ]

        done_count = 0
        for fut in asyncio.as_completed(tasks):
            try:
                r = await fut
                completed.append(asdict(r))
            except Exception as e:
                completed.append({"error": f"{type(e).__name__}: {e}"})
            done_count += 1
            if done_count % LOG_EVERY == 0 or done_count == len(tasks):
                elapsed = time.monotonic() - start_all
                rate = done_count / max(elapsed, 0.001)
                print(
                    f"[{done_count:>4}/{len(tasks)}] "
                    f"elapsed={elapsed:.1f}s  rate={rate:.2f}/s",
                    flush=True,
                )
                # Incremental checkpoint
                OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
                with open(OUT_JSON, "w") as f:
                    json.dump(
                        {
                            "generated_at": datetime.now(timezone.utc).isoformat(),
                            "checkpoint": True,
                            "completed": done_count,
                            "total": len(tasks),
                            "results": completed,
                        },
                        f,
                        indent=2,
                        default=str,
                    )

    wall = time.monotonic() - start_all

    # Sort results to be deterministic by member_id
    completed.sort(key=lambda r: r.get("member_id") or "")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "wall_clock_seconds": round(wall, 2),
                "concurrency": CONCURRENCY,
                "total": len(completed),
                "results": completed,
            },
            f,
            indent=2,
            default=str,
        )
    print(f"Wrote {OUT_JSON}", flush=True)

    report = generate_report(completed, wall)
    with open(OUT_REPORT, "w") as f:
        f.write(report)
    print(f"Wrote {OUT_REPORT}", flush=True)
    print(f"Done in {wall:.1f}s.", flush=True)


if __name__ == "__main__":
    asyncio.run(run())
