"""
Collector registry for Capitol Releases.

Each senator gets a canonical collector assigned in config. The registry
looks up the right collector and provides fallback on degradation.
No runtime waterfall -- known JS sites don't fail through RSS first.
"""

import logging

from pipeline.collectors.base import Collector
from pipeline.collectors.rss_collector import RSSCollector
from pipeline.collectors.httpx_collector import HttpxCollector
from pipeline.collectors.whitehouse_collector import WhitehouseCollector
from pipeline.collectors.tx_senate_collector import TxSenateCollector
from pipeline.collectors.co_caucus_collectors import (
    ColoradoCaucusSquarespaceCollector,
    ColoradoCaucusWixCollector,
    ColoradoCaucusWordPressCollector,
)
from pipeline.collectors.state_legislature_collectors import (
    CaliforniaSenateCollector,
    MissouriSenateNewsroomCollector,
    NebraskaUnicameralCollector,
    OhioSenateCollector,
    WVLegislatureNewsCollector,
)

log = logging.getLogger("capitol.registry")

# Collection methods whose sources are not on a .gov domain, so the shared
# RSS collector's government allowlist would silently discard every item.
_NO_RSS_FALLBACK = {"co_caucus_squarespace", "co_caucus_wp", "co_caucus_wix"}


class CollectorRegistry:
    """Maps senators to their canonical collector."""

    def __init__(self):
        self._rss = RSSCollector()
        self._httpx = HttpxCollector()
        self._whitehouse = WhitehouseCollector()
        self._tx_senate = TxSenateCollector()
        self._ne_unicameral = NebraskaUnicameralCollector()
        self._ca_senate = CaliforniaSenateCollector()
        self._oh_senate = OhioSenateCollector()
        self._mo_senate_newsroom = MissouriSenateNewsroomCollector()
        self._wv_legislature_news = WVLegislatureNewsCollector()
        self._co_caucus_squarespace = ColoradoCaucusSquarespaceCollector()
        self._co_caucus_wp = ColoradoCaucusWordPressCollector()
        self._co_caucus_wix = ColoradoCaucusWixCollector()

    def get_collector(self, senator: dict) -> Collector:
        """Get the canonical collector for a senator based on config."""
        method = senator.get("collection_method", "httpx")

        if method == "rss":
            return self._rss
        elif method == "whitehouse":
            return self._whitehouse
        elif method == "tx_senate":
            return self._tx_senate
        elif method == "ne_unicameral":
            return self._ne_unicameral
        elif method == "ca_senate":
            return self._ca_senate
        elif method == "oh_senate":
            return self._oh_senate
        elif method == "mo_senate_newsroom":
            return self._mo_senate_newsroom
        elif method == "wv_legislature_news":
            return self._wv_legislature_news
        elif method == "co_caucus_squarespace":
            return self._co_caucus_squarespace
        elif method == "co_caucus_wp":
            return self._co_caucus_wp
        elif method == "co_caucus_wix":
            return self._co_caucus_wix
        elif method == "playwright":
            # Playwright collector not yet implemented.
            # Fall back to httpx (works for page 1 on most JS sites)
            # or RSS if available.
            if senator.get("rss_feed_url"):
                return self._rss
            log.debug("Playwright not yet implemented for %s, using httpx", senator["official_id"])
            return self._httpx
        else:
            return self._httpx

    def get_fallback(self, senator: dict) -> Collector | None:
        """Get fallback collector if primary fails."""
        method = senator.get("collection_method", "httpx")
        if method == "rss":
            return self._httpx
        # Two of the Colorado caucus sources publish a working RSS feed, but
        # falling back to it would collect nothing and say so quietly:
        # rss_collector calls classifier.is_external_content(), which
        # allowlists senate.gov / house.gov / whitehouse.gov only, so every
        # .com / .co caucus URL is dropped as third-party content. An
        # explicit no-fallback is better than a silent zero.
        if method in _NO_RSS_FALLBACK:
            return None
        if method != "rss" and senator.get("rss_feed_url"):
            return self._rss
        return None
