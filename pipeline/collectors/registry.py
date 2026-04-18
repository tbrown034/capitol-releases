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

log = logging.getLogger("capitol.registry")


class CollectorRegistry:
    """Maps senators to their canonical collector."""

    def __init__(self):
        self._rss = RSSCollector()
        self._httpx = HttpxCollector()

    def get_collector(self, senator: dict) -> Collector:
        """Get the canonical collector for a senator based on config."""
        method = senator.get("collection_method", "httpx")

        if method == "rss":
            return self._rss
        elif method == "playwright":
            # Playwright collector not yet implemented.
            # Fall back to httpx (works for page 1 on most JS sites)
            # or RSS if available.
            if senator.get("rss_feed_url"):
                return self._rss
            log.debug("Playwright not yet implemented for %s, using httpx", senator["senator_id"])
            return self._httpx
        else:
            return self._httpx

    def get_fallback(self, senator: dict) -> Collector | None:
        """Get fallback collector if primary fails."""
        method = senator.get("collection_method", "httpx")
        if method == "rss":
            return self._httpx
        if method != "rss" and senator.get("rss_feed_url"):
            return self._rss
        return None
