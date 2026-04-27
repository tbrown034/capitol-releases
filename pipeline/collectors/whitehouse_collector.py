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
        """Health-check every configured source independently.

        WH publishes three streams (releases / briefings-statements /
        presidential-actions) on the same Gutenberg deployment. They share
        markup but not state — a renamed selector or empty page on one
        stream wouldn't show up if we only probed sources[0]. Aggregate the
        per-source HealthCheckResults: pass only when every source passes,
        and bubble up the first failure as the headline status.
        """
        sources = (senator.get("scrape_config") or {}).get("sources", [])
        if not sources:
            scoped = dict(senator)
            return await self._httpx.health_check(scoped)

        sid = senator["senator_id"]
        per_source: list[HealthCheckResult] = []
        for src in sources:
            url = src.get("url")
            if not url:
                continue
            scoped = {**senator, "press_release_url": url}
            per_source.append(await self._httpx.health_check(scoped))

        merged = HealthCheckResult(senator_id=sid)
        merged.url_status = max(
            (h.url_status for h in per_source if h.url_status), default=0
        )
        merged.items_found = sum(h.items_found or 0 for h in per_source)
        merged.selector_ok = all(h.selector_ok for h in per_source)
        merged.date_parseable = all(
            (h.date_parseable is not False) for h in per_source
        )
        merged.page_load_ms = (
            sum(h.page_load_ms or 0 for h in per_source) // max(len(per_source), 1)
        )
        first_fail = next(
            (h for h in per_source if not h.selector_ok or h.error_message),
            None,
        )
        if first_fail is not None:
            merged.error_message = (
                first_fail.error_message
                or f"Source failed: {first_fail.items_found} items, status {first_fail.url_status}"
            )
        return merged
