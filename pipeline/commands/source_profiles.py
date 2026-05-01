"""Validate the state source-profile registry.

Usage:
    python -m pipeline source-profiles
"""

from __future__ import annotations

import sys

from pipeline.lib.source_profiles import load_source_profiles, validate_source_profiles


def main() -> None:
    profiles = load_source_profiles()
    result = validate_source_profiles(profiles)
    if result.ok:
        print(f"OK: {result.profile_count} source profiles validated")
        return

    print(f"FAILED: {len(result.errors)} source profile validation errors", file=sys.stderr)
    for error in result.errors:
        print(f"- {error}", file=sys.stderr)
    sys.exit(1)
