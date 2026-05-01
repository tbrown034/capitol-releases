"""State expansion recon generator.

This is a research artifact generator, not production pipeline code. It
builds a machine-usable source inventory for state legislature and
statewide-office expansion planning.

Outputs:
  docs/state-expansion-source-inventory-2026-05-01.json
  docs/state-expansion-source-inventory-2026-05-01.md
  pipeline/recon/state_expansion_source_inventory_2026_05_01.json
  pipeline/recon/state_expansion_source_inventory_2026_05_01.md
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / "docs" / "state-expansion-source-inventory-2026-05-01.json"
OUT_MD = ROOT / "docs" / "state-expansion-source-inventory-2026-05-01.md"
TRACKED_JSON = ROOT / "pipeline" / "recon" / "state_expansion_source_inventory_2026_05_01.json"
TRACKED_MD = ROOT / "pipeline" / "recon" / "state_expansion_source_inventory_2026_05_01.md"

UA = "Mozilla/5.0 (compatible; CapitolReleasesStateRecon/1.0; research)"

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}


@dataclass
class SourceRow:
    source_id: str
    state: str
    office_scope: str
    source_owner: str
    officialness: str
    listing_url: str
    jurisdiction_level: str = "state"
    row_kind: str = "source_profile"
    listing_url_type: str = "press_listing"
    covers_scopes: list[str] | None = None
    roster_url: str | None = None
    detail_url_pattern: str | None = None
    sample_urls: list[str] | None = None
    cms_family: str = "unknown"
    requires_js: bool | None = None
    content_shapes: list[str] | None = None
    frequency_estimate: str = "unknown"
    listing_selectors: list[str] | None = None
    detail_selectors: list[str] | None = None
    pagination: str = "unknown"
    attribution_mode: str = "unknown"
    scraping_strategy: str = "needs_source_profile"
    known_oddities: list[str] | None = None
    implementation_status: str = "needs_profile"
    confidence: str = "low"
    verified_at: str = str(date.today())
    evidence: dict[str, Any] | None = None


LEGISLATURE_SOURCES: list[SourceRow] = [
    SourceRow(
        "tx_senate", "TX", "state_senate", "official_chamber", "official_gov",
        "https://senate.texas.gov/pressroom.php?d=1",
        roster_url="https://www.senate.texas.gov/members.php?lang=en",
        detail_url_pattern="https://senate.texas.gov/pressroom.php?d={district}",
        sample_urls=["https://senate.texas.gov/pressroom.php?d=29"],
        cms_family="static_html",
        content_shapes=["html", "pdf", "video"],
        frequency_estimate="medium",
        listing_selectors=["h3 year headers", "p rows", "p a[href]", r"\d{2}/\d{2}/\d{4}"],
        detail_selectors=["PDF via pdfplumber", "press.php main/body text"],
        pagination="none",
        attribution_mode="direct_member_url",
        scraping_strategy="existing tx_senate_collector",
        implementation_status="implemented_needs_hardening",
        confidence="high",
    ),
    SourceRow(
        "tx_house", "TX", "state_house", "official_chamber", "official_gov",
        "https://house.texas.gov/news/press-releases/",
        roster_url="https://www.house.texas.gov/members",
        detail_url_pattern="https://house.texas.gov/news/press-releases/?id={member_id}",
        sample_urls=["https://house.texas.gov/news/press-releases/"],
        cms_family="unknown",
        content_shapes=["html"],
        frequency_estimate="unknown",
        listing_selectors=["needs profile"],
        detail_selectors=["needs profile"],
        pagination="query id/member filter likely",
        attribution_mode="direct_member_filter",
        scraping_strategy="profile Texas House member id mapping, then httpx listing/detail parser",
        implementation_status="needs_profile",
        confidence="medium",
    ),
    SourceRow(
        "ne_unicameral", "NE", "unicameral", "official_member", "official_gov",
        "https://news.legislature.ne.gov/dist32/",
        roster_url="https://nebraskalegislature.gov/senators/senator_list.php",
        detail_url_pattern="https://news.legislature.ne.gov/dist{district}/",
        sample_urls=["https://news.legislature.ne.gov/dist32/"],
        cms_family="wordpress",
        content_shapes=["html"],
        frequency_estimate="low_medium",
        listing_selectors=["article/post blocks", "entry title anchor", "date text", "Older Entries"],
        detail_selectors=["h1/title", "entry-content or post body"],
        pagination="/page/{n}/ or Older Entries",
        attribution_mode="direct_member_url",
        scraping_strategy="wordpress_member_blog collector; classify newsletters/clips separately",
        implementation_status="ready_first_wave",
        confidence="high",
    ),
    SourceRow(
        "ca_senate", "CA", "state_senate", "official_member", "official_gov",
        "https://sd24.senate.ca.gov/press-releases",
        roster_url="https://www.senate.ca.gov/senators",
        detail_url_pattern="https://sd{district}.senate.ca.gov/news/press-release/{slug}",
        sample_urls=["https://sd24.senate.ca.gov/news/press-release/senator-allen-pursues-stronger-support-mobilehome-residents"],
        cms_family="drupal",
        content_shapes=["html"],
        frequency_estimate="medium_high",
        listing_selectors=["h1 Press Releases", "h3 title", "date text", "summary", "?page=N"],
        detail_selectors=["main/article", "h1 or h2 title", "date near title", "body before Office Information"],
        pagination="?page=N",
        attribution_mode="direct_member_url",
        scraping_strategy="ca_senate_drupal collector",
        implementation_status="ready_first_wave",
        confidence="high",
    ),
    SourceRow(
        "oh_senate", "OH", "state_senate", "official_chamber", "official_gov",
        "https://ohiosenate.gov/members/rob-mccolley/news",
        roster_url="https://ohiosenate.gov/members",
        detail_url_pattern="https://ohiosenate.gov/members/{slug}/news/{slug}",
        sample_urls=["https://ohiosenate.gov/members/rob-mccolley/news"],
        cms_family="aspnet",
        content_shapes=["html", "search_endpoint"],
        frequency_estimate="medium",
        listing_selectors=["embedded searchUpdateUrl", "Results 1 - 25 of N", "date title summary rows"],
        detail_selectors=["detail page body container"],
        pagination="update-search endpoint or page links; page size up to 1000",
        attribution_mode="direct_member_url",
        scraping_strategy="ohio_legislature_search collector using update-search endpoint when possible",
        implementation_status="ready_first_wave",
        confidence="high",
    ),
    SourceRow(
        "mo_senate", "MO", "state_senate", "official_chamber", "official_gov",
        "https://www.senate.mo.gov/media/newsroom",
        roster_url="https://www.senate.mo.gov/Senators",
        detail_url_pattern="https://senate.mo.gov/Media/NewsDetails/{id}",
        sample_urls=["https://senate.mo.gov/Media/NewsDetails/2131", "https://www.senate.mo.gov/Media/CurrentMedia?id=20"],
        cms_family="aspnet",
        content_shapes=["html", "audio", "video"],
        frequency_estimate="high_burst",
        listing_selectors=["newsroom item title/date/summary", "Read More links"],
        detail_selectors=["h1/title", "date", "senator/contact block", "body"],
        pagination="central newsroom plus CurrentMedia?id={memberId}",
        attribution_mode="author_column_or_member_listing",
        scraping_strategy="central_feed_with_member_attribution",
        implementation_status="ready_first_wave",
        confidence="high",
    ),
    SourceRow(
        "or_legislature_press", "OR", "state_legislature", "official_chamber", "official_gov",
        "https://www.oregonlegislature.gov/Pages/pressrelease.aspx",
        row_kind="source_profile",
        listing_url_type="central_press_listing_needs_endpoint_validation",
        covers_scopes=["state_senate", "state_house"],
        roster_url="https://www.oregonlegislature.gov/legislators",
        detail_url_pattern="https://www.oregonlegislature.gov/{member_slug}/Pages/news.aspx",
        sample_urls=["https://www.oregonlegislature.gov/wagner/Pages/news.aspx"],
        cms_family="sharepoint",
        content_shapes=["html", "pdf", "rss"],
        frequency_estimate="medium",
        listing_selectors=["SharePoint list view", "Press Releases by Senator", "PDF document links"],
        detail_selectors=["SharePoint list row or PDF body"],
        pagination="SharePoint PageFirstRow/View GUID; RSS if stable",
        attribution_mode="member_slug_or_caucus_name",
        scraping_strategy="rss_first_sharepoint_list_parser_with_pdf_extraction",
        implementation_status="needs_profile",
        confidence="medium",
        known_oddities=["JS warnings in no-script HTML", "press releases may be PDFs", "downgraded until exact SharePoint/RSS endpoint and sample detail URLs are proven"],
    ),
    SourceRow(
        "pa_senate_gop", "PA", "state_senate", "caucus", "public_caucus",
        "https://www.pasenategop.com/news-releases/",
        roster_url="https://www.pasenategop.com/senators/",
        detail_url_pattern="https://www.pasenategop.com/news/{slug}/",
        sample_urls=["https://www.pasenategop.com/news/senate-republicans-kick-off-2025-26-legislative-session-with-new-members-leadership-team/"],
        cms_family="wordpress",
        content_shapes=["html"],
        frequency_estimate="high",
        listing_selectors=["article/post cards", "date", "h2 title", "Read More"],
        detail_selectors=["h1.entry-title", "posted date", ".entry-content"],
        pagination="/news-releases/page/{n}/",
        attribution_mode="title_prefix_category_or_detail_contact",
        scraping_strategy="wp_caucus_attributed collector",
        implementation_status="ready_first_wave",
        confidence="high",
        known_oddities=["leadership/caucus releases mixed with member releases"],
    ),
    SourceRow(
        "wa_senate_dem", "WA", "state_senate", "caucus", "public_caucus",
        "https://senatedemocrats.wa.gov/wellman/news-releases/",
        roster_url="https://senatedemocrats.wa.gov/senators/",
        detail_url_pattern="https://senatedemocrats.wa.gov/{member_slug}/{yyyy}/{mm}/{dd}/{slug}/",
        sample_urls=["https://senatedemocrats.wa.gov/wellman/2019/09/26/wellman-we-will-not-turn-our-backs-on-our-friends-and-neighbors-who-have-made-washington-their-home/"],
        cms_family="wordpress",
        content_shapes=["html"],
        frequency_estimate="medium_high",
        listing_selectors=["post cards", "date/byline", "Read More", "member slug section"],
        detail_selectors=["h1.entry-title", "date", ".entry-content"],
        pagination="/page/{n}/ likely; WP REST probe needed",
        attribution_mode="direct_member_slug",
        scraping_strategy="wp_member_slug_with_section_filter",
        implementation_status="ready_first_wave",
        confidence="high",
        known_oddities=["News Releases page may include external media/news items for some members"],
    ),
    SourceRow(
        "in_senate_gop", "IN", "state_senate", "caucus", "public_caucus",
        "https://www.indianasenaterepublicans.com/senators",
        roster_url="https://www.indianasenaterepublicans.com/senators",
        detail_url_pattern="https://www.indianasenaterepublicans.com/{slug}",
        sample_urls=["https://www.indianasenaterepublicans.com/mishler-local-students-gain-experience-at-indiana-statehouse"],
        cms_family="unknown_static_or_cms",
        content_shapes=["html"],
        frequency_estimate="medium_high",
        listing_selectors=["senator roster cards", "latest post cards", "Date: text", "Read More"],
        detail_selectors=["h1 title", "body text", "contact block"],
        pagination="needs profile",
        attribution_mode="title_prefix_or_member_slug",
        scraping_strategy="caucus_static_member_slug collector",
        implementation_status="needs_profile",
        confidence="medium",
    ),
    SourceRow(
        "wv_legislature_news", "WV", "state_legislature", "official_chamber", "official_gov",
        "https://www.wvlegislature.gov/News_release/news.cfm",
        row_kind="source_profile",
        listing_url_type="central_press_listing",
        covers_scopes=["state_senate", "state_house"],
        roster_url="https://www.wvlegislature.gov/Senate1/roster.cfm",
        detail_url_pattern="https://www.wvlegislature.gov/News_release/pressrelease.cfm?release={id}",
        sample_urls=["https://www.wvlegislature.gov/News_release/pressrelease.cfm?release=4161"],
        cms_family="coldfusion",
        content_shapes=["html"],
        frequency_estimate="high_institutional_medium_member",
        listing_selectors=["table rows", "Author", "Release", "Date"],
        detail_selectors=["Release Date", "Contact", "author heading", "title", "body"],
        pagination="single central list; query/details by release id",
        attribution_mode="author_column",
        scraping_strategy="central_coldfusion_author_feed with calendar/schedule filters",
        implementation_status="ready_first_wave",
        confidence="high",
        known_oddities=["calendar/schedule posts dominate session feed"],
    ),
    SourceRow(
        "ct_legislature_member_sites", "CT", "state_legislature", "caucus", "public_caucus",
        "https://www.cga.ct.gov/pd/",
        row_kind="directory_profile",
        listing_url_type="member_website_directory",
        covers_scopes=["state_senate", "state_house"],
        roster_url="https://www.cga.ct.gov/asp/menu/cgafindleg.asp",
        detail_url_pattern=None,
        sample_urls=["https://www.cga.ct.gov/pd/"],
        cms_family="mixed",
        content_shapes=["html"],
        frequency_estimate="medium",
        listing_selectors=["committee/member tables link to external member websites"],
        detail_selectors=["depends on caucus domain"],
        pagination="per caucus/member site",
        attribution_mode="direct_member_url_after_roster_mapping",
        scraping_strategy="build caucus source profiles from CGA member website links",
        implementation_status="needs_profile",
        confidence="medium",
        known_oddities=["not pure cga.ct.gov; member websites include senatedems.ct.gov, ctsenaterepublicans.com, housedems.ct.gov, cthousegop.com"],
    ),
]


LEGISLATURE_BUCKETS = {
    "AL": ("B", "B"), "AK": ("B", "B"), "AZ": ("B", "B"), "AR": ("C", "C"),
    "CA": ("A", "B"), "CO": ("B", "B"), "CT": ("B", "B"), "DE": ("B", "B"),
    "FL": ("C", "C"), "GA": ("C", "B"), "HI": ("B", "B"), "ID": ("B", "B"),
    "IL": ("B", "B"), "IN": ("B", "B"), "IA": ("C", "C"), "KS": ("C", "C"),
    "KY": ("C", "C"), "LA": ("C", "C"), "ME": ("B", "B"), "MD": ("B", "C"),
    "MA": ("C", "C"), "MI": ("B", "B"), "MN": ("B", "C"), "MS": ("D", "B_partial"),
    "MO": ("A", "A"), "MT": ("D", "D"), "NE": ("A", "N/A"), "NV": ("B", "B"),
    "NH": ("C", "C"), "NJ": ("B", "B"), "NM": ("B", "B"), "NY": ("A", "A"),
    "NC": ("B", "B"), "ND": ("D", "D"), "OH": ("A", "A"), "OK": ("A", "A"),
    "OR": ("A", "A"), "PA": ("B", "B"), "RI": ("A", "A"), "SC": ("B", "B"),
    "SD": ("C", "C"), "TN": ("B", "B"), "TX": ("A", "A"), "UT": ("C", "C"),
    "VT": ("D", "D"), "VA": ("B", "B"), "WA": ("B", "B"), "WV": ("A", "A"),
    "WI": ("A", "A"), "WY": ("C", "C"),
}


def row_from_bucket(state: str, chamber: str, bucket: str) -> SourceRow:
    owner = {
        "A": "official_chamber",
        "B": "caucus",
        "B_partial": "caucus",
        "C": "official_chamber",
        "D": "unknown",
        "N/A": "unknown",
    }.get(bucket, "unknown")
    status = {
        "A": "needs_profile",
        "B": "needs_profile",
        "B_partial": "needs_profile",
        "C": "do_not_implement_member_claim",
        "D": "do_not_implement_member_claim",
        "N/A": "not_applicable",
    }.get(bucket, "needs_profile")
    strategy = {
        "A": "profile official per-member or central official feed",
        "B": "profile caucus/member sites and attribution rules",
        "B_partial": "profile partial caucus/member availability",
        "C": "leadership/chamber-only collection; no rank-and-file claim",
        "D": "skip rank-and-file member press; executive-first",
        "N/A": "not applicable",
    }.get(bucket, "needs_source_profile")
    return SourceRow(
        source_id=f"{state.lower()}_{chamber}",
        state=state,
        office_scope=chamber,
        source_owner=owner,
        officialness="unknown" if owner == "unknown" else ("official_gov" if owner == "official_chamber" else "public_caucus"),
        listing_url="UNKNOWN_NEEDS_PROFILE",
        row_kind="gap_placeholder",
        listing_url_type="unknown",
        roster_url=None,
        sample_urls=[],
        cms_family="unknown",
        requires_js=None,
        content_shapes=[],
        frequency_estimate="unknown",
        listing_selectors=["needs profile"],
        detail_selectors=["needs profile"],
        pagination="needs profile",
        attribution_mode="unknown",
        scraping_strategy=strategy,
        known_oddities=[],
        implementation_status=status,
        confidence="low" if bucket in {"C", "D"} else "medium",
    )


def detect_cms(html: str, headers: httpx.Headers, url: str) -> str:
    low = html.lower()
    server = headers.get("server", "").lower()
    powered = headers.get("x-powered-by", "").lower()
    if "wp-content" in low or "wp-json" in low or "wordpress" in low:
        return "wordpress"
    if "drupal" in low or "/sites/default/" in low:
        return "drupal"
    if "sharepoint" in low or "_layouts/15" in low or "ms-webpart" in low:
        return "sharepoint"
    if ".cfm" in url.lower() or "coldfusion" in server or "coldfusion" in powered:
        return "coldfusion"
    if "asp.net" in powered or "aspx" in low or ".aspx" in url.lower():
        return "aspnet"
    if "civicplus" in low:
        return "civicplus"
    return "static_or_unknown"


def detect_shapes(html: str, url: str) -> list[str]:
    shapes = {"html"}
    low = html.lower()
    if ".pdf" in low:
        shapes.add("pdf")
    if "rss" in low or "feed" in low:
        shapes.add("rss")
    if "wp-json" in low or "api/" in low or "update-search" in low:
        shapes.add("api")
    if "video" in low or "youtube" in low or "vimeo" in low:
        shapes.add("video")
    if url.lower().endswith(".pdf"):
        shapes = {"pdf"}
    return sorted(shapes)


DATE_RE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+\d{4})\b",
    re.I,
)


def extract_evidence(html: str, url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = soup.get_text(" ", strip=True)
    links = []
    for a in soup.find_all("a", href=True)[:200]:
        label = a.get_text(" ", strip=True)
        href = urljoin(url, a["href"])
        if label and href.startswith("http"):
            links.append({"text": label[:120], "href": href})
    date_matches = DATE_RE.findall(text[:60000])
    return {
        "page_title": title,
        "date_match_count": len(date_matches),
        "first_dates": date_matches[:5],
        "link_count": len(links),
        "sample_links": links[:10],
        "has_no_js_warning": "javascript" in text.lower() and "turn on javascript" in text.lower(),
        "text_chars": len(text),
    }


async def fetch(client: httpx.AsyncClient, row: SourceRow) -> SourceRow:
    if not row.listing_url or row.listing_url == "UNKNOWN_NEEDS_PROFILE":
        row.evidence = {"probe_status": "not_probed", "reason": "no listing_url"}
        return row
    try:
        resp = await client.get(row.listing_url, follow_redirects=True)
        row.evidence = {
            "probe_status": "ok",
            "http_status": resp.status_code,
            "final_url": str(resp.url),
            "content_type": resp.headers.get("content-type"),
        }
        if resp.status_code < 400 and "text/html" in resp.headers.get("content-type", ""):
            html = resp.text
            detected = detect_cms(html, resp.headers, str(resp.url))
            if row.cms_family in {"unknown", "unknown_static_or_cms", "mixed"}:
                row.cms_family = detected
            row.content_shapes = sorted(set((row.content_shapes or []) + detect_shapes(html, str(resp.url))))
            row.requires_js = extract_evidence(html, str(resp.url))["has_no_js_warning"] or False
            row.evidence.update(extract_evidence(html, str(resp.url)))
        else:
            row.evidence.update({"body_probe": "non_html_or_error"})
    except Exception as e:
        row.evidence = {"probe_status": "error", "error": f"{type(e).__name__}: {e}"}
    return row


async def parse_directory(url: str, office_scope: str, source_id_prefix: str) -> list[SourceRow]:
    rows: list[SourceRow] = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": UA}) as client:
        resp = await client.get(url, follow_redirects=True)
    soup = BeautifulSoup(resp.text, "lxml")
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        m = re.search(r"\(([A-Z]{2})\)$", label)
        if not m:
            continue
        state = m.group(1)
        if state not in STATES:
            continue
        href = urljoin(url, a["href"])
        rows.append(SourceRow(
            source_id=f"{state.lower()}_{source_id_prefix}",
            state=state,
            office_scope=office_scope,
            source_owner="executive_office",
            officialness="official_state_portal" if ".gov" in urlparse(href).netloc else "official_directory_link",
            listing_url=href,
            row_kind="directory_profile",
            listing_url_type="office_base_url",
            roster_url=url,
            sample_urls=[href],
            cms_family="unknown",
            content_shapes=[],
            frequency_estimate="unknown",
            listing_selectors=["discover newsroom path from official base URL"],
            detail_selectors=["needs profile"],
            pagination="needs profile",
            attribution_mode="single_office",
            scraping_strategy="discover /news /newsroom /press-releases /media paths then profile",
            implementation_status="needs_profile",
            confidence="medium",
            known_oddities=["directory gives office base URL, not necessarily press listing"],
        ))
    return rows


async def parse_nass_secretaries() -> list[SourceRow]:
    rows: list[SourceRow] = []
    url = "https://www.nass.org/memberships/secretaries-statelieutenant-governors"
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": UA}) as client:
        resp = await client.get(url, follow_redirects=True)
    soup = BeautifulSoup(resp.text, "lxml")
    state_by_name = {v.lower(): k for k, v in STATES.items()}
    for article in soup.select("article.secretary"):
        h2 = article.find("h2")
        if not h2:
            continue
        state_label = h2.get_text(" ", strip=True)
        state_name = re.sub(r"\s*\(CEO\)\s*", "", state_label, flags=re.I)
        state_name = state_name.replace("*", "").strip().lower()
        state = state_by_name.get(state_name)
        if not state:
            continue
        link = h2.find("a", href=True)
        if not link:
            continue
        href = urljoin(url, link["href"])
        role_text = ""
        paragraphs = article.find_all("p")
        if len(paragraphs) > 1:
            role_text = paragraphs[1].get_text(" ", strip=True)
        office_scope = "secretary_of_state"
        if "lt. governor" in role_text.lower() or "lieutenant governor" in role_text.lower():
            office_scope = "lieutenant_governor"
        elif "commonwealth" in role_text.lower():
            office_scope = "secretary_of_commonwealth"
        rows.append(SourceRow(
            source_id=f"{state.lower()}_{office_scope}",
            state=state,
            office_scope=office_scope,
            source_owner="executive_office",
            officialness="official_directory_link",
            listing_url=href,
            row_kind="directory_profile",
            listing_url_type="office_base_url",
            roster_url=url,
            sample_urls=[href],
            cms_family="unknown",
            content_shapes=[],
            frequency_estimate="unknown",
            listing_selectors=["discover newsroom path from NASS office base URL"],
            detail_selectors=["needs profile"],
            pagination="needs profile",
            attribution_mode="single_office",
            scraping_strategy="discover /news /newsroom /press /media path from NASS-listed office URL, then profile",
            implementation_status="needs_profile",
            confidence="medium",
            known_oddities=[
                "NASS identifies chief election officer role and may list lieutenant governor/commonwealth office instead of secretary of state",
                "directory gives office base URL, not necessarily press listing",
            ],
            evidence={"nass_role_text": role_text},
        ))
    return rows


async def parse_nast_treasurers() -> list[SourceRow]:
    rows: list[SourceRow] = []
    url = "https://nast.org/find-your-state-treasurer/"
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": UA}) as client:
        resp = await client.get(url, follow_redirects=True)
    soup = BeautifulSoup(resp.text, "lxml")
    state_by_name = {v: k for k, v in STATES.items()}
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        if label not in state_by_name:
            continue
        state = state_by_name[label]
        href = urljoin(url, a["href"])
        rows.append(SourceRow(
            source_id=f"{state.lower()}_treasurer",
            state=state,
            office_scope="treasurer",
            source_owner="executive_office",
            officialness="official_directory_link",
            listing_url=href,
            row_kind="directory_profile",
            listing_url_type="office_base_url",
            roster_url=url,
            sample_urls=[href],
            cms_family="unknown",
            content_shapes=[],
            frequency_estimate="unknown",
            listing_selectors=["discover newsroom path from treasurer base URL"],
            detail_selectors=["needs profile"],
            pagination="needs profile",
            attribution_mode="single_office",
            scraping_strategy="discover treasury newsroom/press path then profile",
            implementation_status="needs_profile",
            confidence="medium",
            known_oddities=["directory gives office base URL, not necessarily press listing"],
        ))
    return rows


async def main() -> None:
    rows: list[SourceRow] = []
    rows.extend(LEGISLATURE_SOURCES)

    existing = {r.source_id for r in rows}
    covered_chambers = {(r.state, r.office_scope) for r in rows}
    for state, (upper, lower) in LEGISLATURE_BUCKETS.items():
        for chamber, bucket in [("state_senate", upper), ("state_house", lower)]:
            if bucket == "N/A":
                continue
            sid = f"{state.lower()}_{chamber}"
            if (
                sid not in existing
                and (state, chamber) not in covered_chambers
                and not (state == "NE" and chamber == "state_senate")
            ):
                rows.append(row_from_bucket(state, chamber, bucket))

    rows.extend(await parse_directory("https://www.usa.gov/state-governor", "governor", "governor"))
    rows.extend(await parse_directory("https://www.usa.gov/state-attorney-general", "attorney_general", "attorney_general"))
    rows.extend(await parse_nass_secretaries())
    rows.extend(await parse_nast_treasurers())

    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": UA}) as client:
        probed = await asyncio.gather(*(fetch(client, row) for row in rows))

    data = [asdict(r) for r in probed]
    rendered_json = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    OUT_JSON.write_text(rendered_json)
    TRACKED_JSON.write_text(rendered_json)

    ready = [r for r in probed if r.implementation_status == "ready_first_wave"]
    needs = [r for r in probed if r.implementation_status == "needs_profile"]
    blocked = [r for r in probed if r.implementation_status == "do_not_implement_member_claim"]

    lines = [
        "# State Expansion Source Inventory",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        f"- Total rows: {len(probed)}",
        f"- Ready first wave: {len(ready)}",
        f"- Implemented, needs hardening: {sum(1 for r in probed if r.implementation_status == 'implemented_needs_hardening')}",
        f"- Needs source profile: {len(needs)}",
        f"- Do not implement rank-and-file member claim: {len(blocked)}",
        f"- Gap placeholders: {sum(1 for r in probed if r.row_kind == 'gap_placeholder')}",
        f"- Directory/base URL rows: {sum(1 for r in probed if r.listing_url_type == 'office_base_url')}",
        "",
        "## Ready / High-Confidence Rows",
        "",
        "| Source | Scope | URL | CMS | Strategy | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    for r in ready:
        ev = r.evidence or {}
        evidence = f"HTTP {ev.get('http_status', '?')}; dates={ev.get('date_match_count', '?')}; links={ev.get('link_count', '?')}"
        lines.append(
            f"| `{r.source_id}` | {r.office_scope} | {r.listing_url} | {r.cms_family} | {r.scraping_strategy} | {evidence} |"
        )
    lines.extend([
        "",
        "## Rows Needing Profile",
        "",
        "| Source | Scope | Status | URL | Strategy |",
        "|---|---|---|---|---|",
    ])
    for r in needs:
        lines.append(f"| `{r.source_id}` | {r.office_scope} | {r.confidence} | {r.listing_url} | {r.scraping_strategy} |")
    rendered_md = "\n".join(lines) + "\n"
    OUT_MD.write_text(rendered_md)
    TRACKED_MD.write_text(rendered_md)


if __name__ == "__main__":
    asyncio.run(main())
