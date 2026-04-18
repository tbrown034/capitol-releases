"""
Collector registry for Capitol Releases.

Each senator gets a canonical collector assigned in config. The registry
looks up the right collector and provides fallback on degradation.
No runtime waterfall -- known JS sites don't fail through RSS first.
"""

import logging

from pipeline.collectors.base import Collector
from pipeline.collectors.rss_collector import RSSCollector

log = logging.getLogger("capitol.registry")

# Lazy imports for optional collectors
_httpx_collector = None
_playwright_collector = None


class CollectorRegistry:
    """Maps senators to their canonical collector."""

    def __init__(self):
        self._rss = RSSCollector()

    def get_collector(self, senator: dict) -> Collector:
        """Get the canonical collector for a senator based on config."""
        method = senator.get("collection_method", "httpx")

        if method == "rss":
            return self._rss
        elif method == "playwright":
            log.info(
                "Playwright requested for %s but not yet implemented, falling back to RSS/httpx",
                senator["senator_id"],
            )
            # Playwright collector will be added in a future phase
            if senator.get("rss_feed_url"):
                return self._rss
            return self._rss  # placeholder
        else:
            # httpx collector will be refactored from backfill.py
            # For now, if they have RSS, use that
            if senator.get("rss_feed_url"):
                log.debug("httpx senator %s has RSS, using RSS", senator["senator_id"])
                return self._rss
            log.info(
                "httpx collector not yet refactored for %s, skipping",
                senator["senator_id"],
            )
            return self._rss  # placeholder

    def get_fallback(self, senator: dict) -> Collector | None:
        """Get fallback collector if primary fails."""
        method = senator.get("collection_method", "httpx")
        # If primary was RSS, fallback is httpx (once implemented)
        # If primary was httpx, fallback is RSS (if available)
        if method != "rss" and senator.get("rss_feed_url"):
            return self._rss
        return None
