"""White House collector.

The White House publishes three distinct streams — press releases,
briefings & statements, and presidential actions — under different URL
paths on the same Gutenberg WordPress site. This collector iterates
`scrape_config.sources` and delegates each source to HttpxCollector.

Content type per record is resolved by URL rules in classifier.py
(/briefings-statements/ -> statement, /presidential-actions/ ->
presidential_action, everything else defaults to press_release).
"""

import logging
import time
from datetime import datetime

from pipeline.collectors.base import CollectorResult, HealthCheckResult
from pipeline.collectors.httpx_collector import HttpxCollector

log = logging.getLogger("capitol.collector.whitehouse")


class WhitehouseCollector:
    """Multi-URL HTTP collector for the White House."""

    def __init__(self):
        self._httpx = HttpxCollector()

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        start = time.monotonic()
        sid = senator["senator_id"]
        sources = (senator.get("scrape_config") or {}).get("sources", [])
        merged = CollectorResult(senator_id=sid, method="whitehouse")

        if not sources:
            merged.errors.append("No scrape_config.sources configured")
            return merged

        for src in sources:
            url = src.get("url")
            if not url:
                continue
            scoped = {**senator, "press_release_url": url}
            try:
                r = await self._httpx.collect(scoped, since=since, max_pages=max_pages)
            except Exception as e:
                merged.errors.append(f"{url}: {type(e).__name__}: {e}")
                continue
            merged.releases.extend(r.releases)
            merged.errors.extend(f"{url}: {err}" for err in r.errors)
            merged.pages_scraped += r.pages_scraped

        merged.duration_seconds = time.monotonic() - start
        log.info(
            "whitehouse collected %d releases for %s across %d sources (%.1fs)",
            len(merged.releases), sid, len(sources), merged.duration_seconds,
        )
        return merged

    async def health_check(self, senator: dict) -> HealthCheckResult:
        """Health-check the first configured source.

        WH streams share a WordPress deployment — one probe is enough
        to catch an outage.
        """
        sources = (senator.get("scrape_config") or {}).get("sources", [])
        scoped = dict(senator)
        if sources:
            scoped["press_release_url"] = sources[0].get(
                "url", scoped.get("press_release_url", "")
            )
        return await self._httpx.health_check(scoped)
