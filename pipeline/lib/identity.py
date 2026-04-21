"""
Document identity for Capitol Releases.

Provides URL normalization and content fingerprinting for deduplication.
source_url UNIQUE is necessary but not sufficient -- Senate sites change
paths, append query params, and republish content. This module provides
stronger identity guarantees.
"""

import hashlib
import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


# Query params that are safe to strip (tracking, pagination, cache-busting)
_STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "fbclid", "gclid", "mc_cid", "mc_eid",
    "_ga", "_gl", "ref", "source",
    "et_blog",  # WordPress Divi pagination artifact
}


def normalize_url(url: str) -> str:
    """Normalize a URL for consistent deduplication.

    - Lowercases scheme and host
    - Upgrades http -> https for senate.gov domains (the real canonical)
    - Lowercases query param KEYS so ?id= and ?ID= dedup
    - Strips tracking query params (utm_*, fbclid, etc.)
    - Removes trailing slashes from path
    - Removes fragment (#)
    """
    if not url:
        return ""

    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    if scheme == "http" and (netloc.endswith(".senate.gov") or netloc.endswith(".gov")):
        scheme = "https"

    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {
            k.lower(): v for k, v in params.items()
            if k.lower() not in _STRIP_PARAMS
        }
        query = urlencode(filtered, doseq=True) if filtered else ""
    else:
        query = ""

    return urlunparse((scheme, netloc, path, "", query, ""))


def content_hash(text: str) -> str:
    """Generate a SHA-256 hash of content for change detection.

    Normalizes whitespace before hashing so minor formatting changes
    don't produce false positives.
    """
    if not text:
        return ""
    normalized = re.sub(r"\s+", " ", text.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_likely_duplicate(
    senator_id: str,
    title: str,
    existing_titles: set[str],
) -> bool:
    """Check if a title is likely a duplicate of an existing record.

    Uses normalized title comparison as a secondary check beyond URL dedup.
    Useful for catching republished content at different URLs.
    """
    normalized = _normalize_title(title)
    key = f"{senator_id}:{normalized}"
    return key in existing_titles


def make_title_key(senator_id: str, title: str) -> str:
    """Create a normalized title key for duplicate checking."""
    return f"{senator_id}:{_normalize_title(title)}"


def _normalize_title(title: str) -> str:
    """Normalize a title for comparison (lowercase, strip punctuation, collapse whitespace)."""
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"[^\w\s]", "", t)  # remove punctuation
    t = re.sub(r"\s+", " ", t)     # collapse whitespace
    return t
