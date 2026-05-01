"""State source-profile registry loading and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

SEED_PATH = Path(__file__).resolve().parent.parent / "seeds" / "state_source_profiles.json"

READY_STATUSES = {"ready_first_wave", "implemented_needs_hardening"}
DETERMINISTIC_ATTRIBUTION_MODES = {
    "direct_member_url",
    "author_column",
    "author_column_or_member_listing",
    "title_prefix",
    "title_prefix_category_or_detail_contact",
    "category_tag",
    "single_office",
    "chamber_only",
    "direct_member_slug",
}

REQUIRED_PROFILE_FIELDS = {
    "source_id",
    "state",
    "jurisdiction_level",
    "row_kind",
    "office_scope",
    "source_owner",
    "officialness",
    "roster_url",
    "listing_url",
    "listing_url_type",
    "covers_scopes",
    "detail_url_pattern",
    "sample_urls",
    "cms_family",
    "requires_js",
    "content_shapes",
    "frequency_estimate",
    "listing_selectors",
    "detail_selectors",
    "pagination",
    "attribution_mode",
    "scraping_strategy",
    "known_oddities",
    "implementation_status",
    "confidence",
    "verified_at",
}


@dataclass(frozen=True)
class ValidationResult:
    profile_count: int
    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def load_source_profiles(path: Path = SEED_PATH) -> list[dict[str, Any]]:
    """Load registered state source profiles."""
    data = json.loads(path.read_text())
    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError(f"{path} must contain a top-level profiles list")
    return profiles


def get_source_profile(source_id: str, path: Path = SEED_PATH) -> dict[str, Any]:
    """Return one profile by source_id."""
    for profile in load_source_profiles(path):
        if profile.get("source_id") == source_id:
            return profile
    raise KeyError(source_id)


def validate_source_profiles(profiles: list[dict[str, Any]]) -> ValidationResult:
    """Validate registry rows against the state expansion readiness schema."""
    errors: list[str] = []
    seen: set[str] = set()

    for index, profile in enumerate(profiles):
        source_id = profile.get("source_id") or f"<row {index}>"

        missing = sorted(REQUIRED_PROFILE_FIELDS - profile.keys())
        if missing:
            errors.append(f"{source_id}: missing required fields: {', '.join(missing)}")
            continue

        duplicate = source_id in seen
        if duplicate:
            errors.append(f"{source_id}: duplicate source_id")
        seen.add(source_id)

        _validate_required_values(source_id, profile, errors)
        _validate_ready_standard(source_id, profile, errors)

    return ValidationResult(profile_count=len(profiles), errors=errors)


def _validate_required_values(source_id: str, profile: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(profile["source_id"], str) or not profile["source_id"].strip():
        errors.append(f"{source_id}: source_id must be a non-empty string")
    if not isinstance(profile["state"], str) or len(profile["state"]) != 2 or not profile["state"].isupper():
        errors.append(f"{source_id}: state must be a two-letter uppercase code")
    if profile["jurisdiction_level"] != "state":
        errors.append(f"{source_id}: jurisdiction_level must be state")
    if profile["row_kind"] != "source_profile":
        errors.append(f"{source_id}: row_kind must be source_profile")
    if profile["source_owner"] == "unknown":
        errors.append(f"{source_id}: source_owner must be explicit")
    if profile["officialness"] == "unknown":
        errors.append(f"{source_id}: officialness must be explicit")
    if profile["cms_family"] == "unknown":
        errors.append(f"{source_id}: cms_family must be explicit")
    if not isinstance(profile["requires_js"], bool):
        errors.append(f"{source_id}: requires_js must be boolean")
    if profile["confidence"] not in {"high", "medium", "low"}:
        errors.append(f"{source_id}: confidence must be high, medium, or low")

    for field in ("listing_url", "roster_url", "detail_url_pattern"):
        if not _is_urlish(profile[field]):
            errors.append(f"{source_id}: {field} must be a URL or URL pattern")

    for field in ("sample_urls", "content_shapes", "listing_selectors", "detail_selectors", "known_oddities"):
        if not isinstance(profile[field], list):
            errors.append(f"{source_id}: {field} must be a list")
        elif field != "known_oddities" and not profile[field]:
            errors.append(f"{source_id}: {field} must not be empty")

    if not isinstance(profile["covers_scopes"], list):
        errors.append(f"{source_id}: covers_scopes must be a list")
    if profile["listing_url_type"] == "central_press_listing" and not profile["covers_scopes"]:
        errors.append(f"{source_id}: central listings must declare covers_scopes")

    try:
        date.fromisoformat(profile["verified_at"])
    except (TypeError, ValueError):
        errors.append(f"{source_id}: verified_at must be an ISO date")


def _validate_ready_standard(source_id: str, profile: dict[str, Any], errors: list[str]) -> None:
    if profile["implementation_status"] not in READY_STATUSES:
        errors.append(f"{source_id}: implementation_status is not ready for the source-profile registry")
    if profile["listing_url_type"] == "unknown" or not _is_urlish(profile["listing_url"]):
        errors.append(f"{source_id}: listing URL must be known")
    if not profile["sample_urls"]:
        errors.append(f"{source_id}: at least one sample URL is required")
    if _unknownish(profile["detail_selectors"]):
        errors.append(f"{source_id}: date/title/body extraction pattern must be known")
    if _unknownish(profile["pagination"]):
        errors.append(f"{source_id}: pagination or API strategy must be known")
    if profile["attribution_mode"] not in DETERMINISTIC_ATTRIBUTION_MODES:
        errors.append(f"{source_id}: attribution_mode must be deterministic")
    if profile["source_owner"] == "unknown" or profile["officialness"] == "unknown":
        errors.append(f"{source_id}: source owner and officialness must be explicit")


def _is_urlish(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _unknownish(value: Any) -> bool:
    if isinstance(value, str):
        return not value.strip() or value.strip().lower() == "unknown"
    if isinstance(value, list):
        return not value or any(_unknownish(item) for item in value)
    return value is None
