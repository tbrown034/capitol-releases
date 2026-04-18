"""
Base collector protocol and shared data structures.

Every collector implements the same interface: collect() and health_check().
The registry assigns each senator a canonical collector based on their
collection_method config.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


@dataclass
class ReleaseRecord:
    """A single collected press release, ready for DB insertion."""
    senator_id: str
    title: str
    source_url: str
    published_at: datetime | None = None
    body_text: str = ""
    raw_html: str = ""
    content_type: str = "press_release"
    date_source: str = ""
    date_confidence: float = 0.0
    content_hash: str = ""


@dataclass
class CollectorResult:
    """Result of a collection run for one senator."""
    senator_id: str
    method: str                          # rss, httpx, playwright
    releases: list[ReleaseRecord] = field(default_factory=list)
    pages_scraped: int = 0
    inserted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


@dataclass
class HealthCheckResult:
    """Result of a health check for one senator."""
    senator_id: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    url_status: int = 0
    selector_ok: bool = False
    items_found: int = 0
    date_parseable: bool = False
    page_load_ms: int = 0
    error_message: str = ""

    @property
    def passed(self) -> bool:
        return self.url_status == 200 and self.items_found > 0


class Collector(Protocol):
    """Protocol that all collectors must implement."""

    async def collect(
        self,
        senator: dict,
        since: datetime | None = None,
        max_pages: int = 1,
    ) -> CollectorResult:
        """Collect releases for a senator.

        Args:
            senator: Senator config dict from senate.json
            since: Only collect releases after this date (for incremental updates)
            max_pages: Maximum pages to scrape (1 for daily updates, more for backfill)
        """
        ...

    async def health_check(self, senator: dict) -> HealthCheckResult:
        """Check if the collection method is working for this senator."""
        ...
