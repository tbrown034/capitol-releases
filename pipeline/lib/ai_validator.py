"""
AI validation layer for Capitol Releases.

Uses Claude Haiku for post-collection quality validation. This is an
advisory layer -- it flags questionable records for review but never
silently modifies the production corpus.

Validates:
- Is this title actually a press release title?
- Is the date plausible?
- Is the body text real content or nav/footer/boilerplate?
- Is the content type classification correct?

Records below confidence threshold go to quarantine (flagged), not rejected.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("capitol.ai")

# Load .env for API key
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


@dataclass
class ValidationResult:
    """Result of AI validation for a single record."""
    index: int
    confidence: float        # 0.0-1.0 overall
    is_real_release: bool
    date_plausible: bool
    body_is_content: bool
    suggested_type: str      # AI's opinion on content_type
    issues: list[str]


def validate_batch(releases: list[dict], senator_name: str = "") -> list[ValidationResult]:
    """Validate a batch of extracted releases using Claude Haiku.

    Args:
        releases: list of dicts with keys: title, published_at, body_text_preview, content_type, source_url
        senator_name: senator's full name for context

    Returns:
        list of ValidationResult, one per input release
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.debug("No ANTHROPIC_API_KEY, skipping AI validation")
        return []

    try:
        import anthropic
    except ImportError:
        log.debug("anthropic package not installed, skipping AI validation")
        return []

    # Prepare the batch for the API
    items_for_review = []
    for i, r in enumerate(releases):
        body_preview = (r.get("body_text", "") or "")[:200]
        items_for_review.append({
            "index": i,
            "title": r.get("title", ""),
            "date": r.get("published_at", ""),
            "body_preview": body_preview,
            "content_type": r.get("content_type", "press_release"),
            "url": r.get("source_url", ""),
        })

    if not items_for_review:
        return []

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    prompt = f"""You are validating scraped press releases from U.S. Senator {senator_name or 'unknown'}.
Today's date is {today}.

For each item below, evaluate:
1. Is this a real press release, statement, or official communication? (not nav text, footer, error page, etc.)
2. Is the date plausible? (should be between 2024-01-01 and today)
3. Does the body preview look like actual content? (not boilerplate, nav links, cookie notices)
4. What content type best fits? (press_release, statement, op_ed, letter, photo_release, floor_statement, other)

Items to validate:
{json.dumps(items_for_review, indent=2)}

Respond with a JSON array. Each element must have:
- index (int)
- confidence (float 0-1)
- is_real_release (bool)
- date_plausible (bool)
- body_is_content (bool)
- suggested_type (string)
- issues (list of strings, empty if no issues)

Return ONLY the JSON array, no other text."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse the response
        text = response.content[0].text.strip()
        # Handle potential markdown code blocks
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        results_data = json.loads(text)
        results = []
        for item in results_data:
            results.append(ValidationResult(
                index=item["index"],
                confidence=item["confidence"],
                is_real_release=item["is_real_release"],
                date_plausible=item["date_plausible"],
                body_is_content=item["body_is_content"],
                suggested_type=item["suggested_type"],
                issues=item.get("issues", []),
            ))

        log.info(
            "AI validated %d items. Avg confidence: %.2f",
            len(results),
            sum(r.confidence for r in results) / len(results) if results else 0,
        )
        return results

    except json.JSONDecodeError as e:
        log.error("AI response was not valid JSON: %s", e)
        return []
    except Exception as e:
        log.error("AI validation failed: %s: %s", type(e).__name__, e)
        return []


def flag_low_confidence(conn, release_id: str, confidence: float, issues: list[str]):
    """Flag a record as low confidence in the database."""
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE press_releases
            SET extraction_confidence = %s,
                updated_at = NOW()
            WHERE id = %s::uuid
        """, (confidence, release_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error("Failed to flag record %s: %s", release_id, e)
    finally:
        cur.close()
