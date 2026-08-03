"""
Unit tests for date extraction. No database or network required:

    .venv/bin/python -m pytest pipeline/tests/test_dates.py -q

These lock in the three extraction bugs found on 2026-07-25:

1. `_nearby_date_text` climbed into the wrapper holding every card on a
   listing page, so all ~20 rows on a page inherited the first card's
   date (1,253 rows across 17 House members).
2. The House `documentsingle.aspx` template hardcodes
   `datetime="2017-11-13"` on every `<time>` while the visible text
   carries the real date, and renders a related-news rail ahead of the
   article, so an unscoped `<time>` read buried live releases in 2017.
3. `extract_date_from_html` returned the first structurally valid
   candidate even when it was absurd, so a future-dated meta tag won over
   a correct body dateline.
"""

from datetime import datetime, timezone

from bs4 import BeautifulSoup

from pipeline.backfill import _nearby_date_text, extract_listing_items
from pipeline.lib.classifier import looks_like_article_url
from pipeline.lib.dates import extract_date_from_html, is_plausible_date


def soup(html):
    return BeautifulSoup(html, "lxml")


# --- listing-row date locality -------------------------------------------

# Shape of frost.house.gov / takano.house.gov: a flat container where each
# release is a date span, an h2.title, and a summary paragraph.
LISTING_HTML = """
<div class="view-content">
  <span class="date black">July 20, 2026</span>
  <h2 class="title"><a href="/media/press-releases/first">First release</a></h2>
  <p class="summary">Summary one.</p>
  <span class="date black">June 30, 2026</span>
  <h2 class="title"><a href="/media/press-releases/second">Second release</a></h2>
  <p class="summary">Summary two.</p>
  <span class="date black">June 25, 2026</span>
  <h2 class="title"><a href="/media/press-releases/third">Third release</a></h2>
  <p class="summary">Summary three.</p>
</div>
"""


def test_listing_rows_get_their_own_dates():
    items = extract_listing_items(soup(LISTING_HTML), {"list_item": "h2.title"})
    assert len(items) == 3
    dates = [_nearby_date_text(i) for i in items]
    assert dates == ["July 20, 2026", "June 30, 2026", "June 25, 2026"], (
        "each listing row must take the date of its own sibling, not the "
        "first date in the shared parent container"
    )


def test_parent_walk_stops_at_multi_item_container():
    """A parent holding several rows must not donate its date to one row."""
    html = """
    <div class="wrap">
      <span class="date">March 3, 2026</span>
      <div class="rows">
        <h2 class="title"><a href="/a">A</a></h2>
        <h2 class="title"><a href="/b">B</a></h2>
      </div>
    </div>
    """
    items = extract_listing_items(soup(html), {"list_item": "h2.title"})
    assert [_nearby_date_text(i) for i in items] == ["", ""]


# --- <time> element traps -------------------------------------------------

def test_time_attribute_contradicting_its_text_is_ignored():
    """documentsingle.aspx emits a constant datetime with real visible text."""
    html = """
    <main>
      <div class="news-related-news">
        <div class="newsdetails"><time datetime="2017-11-13">December 2, 2025</time></div>
      </div>
      <div class="article">
        <h2>Latta Introduces Wi-Fi Bill</h2>
        <p>Washington, June 4, 2026 Today, Congressman Bob Latta introduced.</p>
      </div>
    </main>
    """
    result = extract_date_from_html(soup(html))
    assert result is not None
    assert result.value.date() == datetime(2026, 6, 4).date()


def test_time_in_related_rail_is_skipped():
    html = """
    <main>
      <aside class="related-posts">
        <time datetime="2025-01-05">January 5, 2025</time>
      </aside>
      <article>
        <time datetime="2026-06-04">June 4, 2026</time>
      </article>
    </main>
    """
    result = extract_date_from_html(soup(html))
    assert result.value.date() == datetime(2026, 6, 4).date()
    assert result.source == "time_element"


def test_consistent_time_element_still_trusted():
    html = '<main><article><time datetime="2026-05-20">May 20, 2026</time></article></main>'
    result = extract_date_from_html(soup(html))
    assert result.value.date() == datetime(2026, 5, 20).date()
    assert result.confidence == 0.90


# --- plausibility gating --------------------------------------------------

def test_meta_tag_still_wins_when_plausible():
    html = """
    <html><head>
      <meta property="article:published_time" content="2026-05-14T10:00:00-04:00"/>
    </head><body><main><p>Washington, June 4, 2026 text.</p></main></body></html>
    """
    result = extract_date_from_html(soup(html))
    assert result.source == "meta_tag"
    assert result.confidence == 0.95


def test_absurd_meta_falls_through_to_body_dateline():
    """A far-future meta must not beat a plausible dateline in the body."""
    html = """
    <html><head>
      <meta property="article:published_time" content="2029-02-03T10:00:00Z"/>
    </head><body><main><p>Washington, June 4, 2026 the congressman said.</p></main></body></html>
    """
    result = extract_date_from_html(soup(html))
    assert result.value.date() == datetime(2026, 6, 4).date()
    assert result.source == "page_text"


def test_implausible_candidate_returned_when_nothing_better():
    """Never silently drop a date we did extract — keep it for the audit trail."""
    html = """
    <html><head>
      <meta property="article:published_time" content="2029-02-03T10:00:00Z"/>
    </head><body><main><p>No dateline here.</p></main></body></html>
    """
    result = extract_date_from_html(soup(html))
    assert result is not None
    assert result.value.year == 2029


def test_is_plausible_date_bounds():
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    assert is_plausible_date(datetime(2026, 6, 4, tzinfo=timezone.utc), now)
    assert not is_plausible_date(datetime(1999, 1, 1, tzinfo=timezone.utc), now)
    assert not is_plausible_date(datetime(2026, 9, 24, tzinfo=timezone.utc), now)
    assert not is_plausible_date(None, now)


# --- navigation-row rejection --------------------------------------------

def test_article_urls_accepted_and_nav_urls_rejected():
    articles = [
        "https://www.king.senate.gov/newsroom/press-releases/king-pingree-announce-more-funding",
        "https://himes.house.gov/newsroom?ID=3145CCF3-9D13-4D1F-9202-FF503C8F34BD",
        "https://www.moody.senate.gov/press-releases/video-release-senator-moody-continues",
    ]
    nav = [
        "https://www.crapo.senate.gov/media/newsreleases",
        "https://goodlander.house.gov/media/in-the-news/",
        "https://www.tillis.senate.gov/climate-change",
        "https://www.klobuchar.senate.gov/public/index.cfm/flag-requests",
        "https://emmer.house.gov/media-center/videos/otsego-district-office",
    ]
    assert all(looks_like_article_url(u) for u in articles)
    assert not any(looks_like_article_url(u) for u in nav)
