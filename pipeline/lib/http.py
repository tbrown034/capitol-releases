"""
Shared HTTP client for Capitol Releases pipeline.

Provides a configured httpx client with retry logic, consistent headers,
and politeness delays. Replaces duplicated HEADERS dicts and bare
httpx.AsyncClient() calls across 4 scripts.
"""

import asyncio
import logging

import httpx

log = logging.getLogger("capitol.http")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Note: Brotli is intentionally omitted. httpx decodes gzip/deflate
    # natively but needs the optional `brotli` (or `brotlicffi`) package to
    # decode `br`. Without it, advertising `br` causes Cloudflare-fronted
    # sites (whitehouse.gov today) to ship Brotli bytes that we then parse
    # as garbage HTML, silently producing 0-item health checks. Until/unless
    # brotli is added to requirements, only advertise what we can decode.
    "Accept-Encoding": "gzip, deflate",
}

DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_POLITENESS_DELAY = 0.5

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_RETRYABLE_EXCEPTIONS = (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)


def create_client(timeout: float = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    """Create a configured async HTTP client."""
    return httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
    )


async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base: float = 2.0,
) -> httpx.Response:
    """Fetch a URL with exponential backoff retry on transient errors.

    Retries on: timeouts, connection errors, 429/5xx responses.
    Raises on: permanent failures (4xx except 429), exhausted retries.
    """
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.get(url)
            if resp.status_code in _RETRYABLE_STATUS_CODES:
                log.warning(
                    "Retryable HTTP %d from %s (attempt %d/%d)",
                    resp.status_code, url, attempt, max_retries,
                )
                if attempt < max_retries:
                    await asyncio.sleep(backoff_base ** attempt)
                    continue
                return resp  # return last response even if retryable
            return resp
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            log.warning(
                "Request failed for %s: %s (attempt %d/%d)",
                url, type(exc).__name__, attempt, max_retries,
            )
            if attempt < max_retries:
                await asyncio.sleep(backoff_base ** attempt)

    # All retries exhausted
    if last_exc:
        raise last_exc
    raise httpx.ReadError(f"All {max_retries} retries exhausted for {url}")


async def politeness_delay(seconds: float = DEFAULT_POLITENESS_DELAY):
    """Async sleep for politeness between requests."""
    await asyncio.sleep(seconds)
