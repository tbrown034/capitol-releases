"""
Content type classification for Capitol Releases.

Classifies press releases, statements, op-eds, letters, photo releases,
and floor statements based on title prefixes, URL paths, and categories.

The approach is rule-based and deterministic. AI refinement happens
separately as an advisory layer, not in the hot path.
"""

import re

# Content types in order of specificity
CONTENT_TYPES = [
    "press_release",
    "statement",
    "op_ed",
    "letter",
    "photo_release",
    "floor_statement",
    "presidential_action",
    "other",
]

# Title prefix patterns (case-insensitive). Anchored patterns are preferred --
# unanchored \bOP-ED\b and \bletter\b phrases tend to match quotes and references
# to someone ELSE's op-ed/letter, which violates the "original content only" rule.
_TITLE_RULES: list[tuple[re.Pattern, str]] = [
    # Explicit prefix labels -- strongest signal
    (re.compile(r"^(?:PHOTO\s*(?:RELEASE)?)\s*:", re.I), "photo_release"),
    (re.compile(r"^(?:OP[- ]?ED)\s*:", re.I), "op_ed"),
    (re.compile(r"^(?:COMMENTARY)\s*:", re.I), "op_ed"),
    (re.compile(r"^(?:LETTER)\s*:", re.I), "letter"),
    (re.compile(r"^(?:FLOOR\s+STATEMENT)\s*:", re.I), "floor_statement"),
    (re.compile(r"^(?:STATEMENT)\s*:", re.I), "statement"),
    # "Senator X pens/authors/writes op-ed" -- subject anchored, first-person authorship
    (re.compile(r"\b(?:pens?|authors?|wrote|writes)\s+op[- ]?ed\b", re.I), "op_ed"),
    (re.compile(r"\bop[- ]?ed\s+by\s+(?:sen\.?|senator)\b", re.I), "op_ed"),
    # Floor remarks -- safe; rarely a quote
    (re.compile(r"\b(?:delivers?|gives?|made)\s+(?:floor\s+)?(?:speech|statement|remarks)\b", re.I), "floor_statement"),
    (re.compile(r"^floor (?:speech|statement|remarks)\b", re.I), "floor_statement"),
    # Letter -- requires senator-as-subject verb; "in letter to" removed
    # (previously matched quoted references to someone else's letter).
    (re.compile(r"\b(?:sends?|sent|signs?|led|leads?)\s+letter(?:s)?\s+to\b", re.I), "letter"),
    (re.compile(r"^letter\s+to\b", re.I), "letter"),
]

# URL path patterns
_URL_RULES: list[tuple[str, str]] = [
    ("/op-ed", "op_ed"),
    ("/op_ed", "op_ed"),
    ("/commentary", "op_ed"),
    ("/floor-statement", "floor_statement"),
    ("/floor-speech", "floor_statement"),
    ("/speeches", "floor_statement"),
    ("/letter", "letter"),
    ("/photo-release", "photo_release"),
    ("/presidential-actions/", "presidential_action"),
    ("/briefings-statements/", "statement"),
]

# WordPress category mappings
_CATEGORY_MAP: dict[str, str] = {
    "press releases": "press_release",
    "press release": "press_release",
    "statements": "statement",
    "statement": "statement",
    "op-eds": "op_ed",
    "op-ed": "op_ed",
    "commentary": "op_ed",
    "commentaries": "op_ed",
    "letters": "letter",
    "letter": "letter",
    "floor statements": "floor_statement",
    "floor statement": "floor_statement",
    "speeches": "floor_statement",
    "speech": "floor_statement",
    "photo releases": "photo_release",
    "photo release": "photo_release",
}


def classify_content_type(
    title: str = "",
    url: str = "",
    categories: list[str] | None = None,
) -> str:
    """Classify a press release into a content type.

    Uses title prefixes first (strongest signal), then URL paths,
    then WordPress categories. Defaults to 'press_release'.
    """
    # 1. Title prefix rules (strongest signal)
    if title:
        for pattern, content_type in _TITLE_RULES:
            if pattern.search(title):
                return content_type

    # 2. URL path rules
    if url:
        url_lower = url.lower()
        for path_fragment, content_type in _URL_RULES:
            if path_fragment in url_lower:
                return content_type

    # 3. WordPress category tags
    if categories:
        for cat in categories:
            mapped = _CATEGORY_MAP.get(cat.lower().strip())
            if mapped:
                return mapped

    return "press_release"


def is_external_content(url: str, title: str = "") -> bool:
    """Check if a URL points to external content (not senator-produced).

    Used to filter out 'In the News' links to external media coverage.
    """
    if not url:
        return False
    url_lower = url.lower()
    # External domains (not .gov)
    allowed_gov = ("senate.gov", "house.gov", "whitehouse.gov")
    if not any(d in url_lower for d in allowed_gov):
        if any(d in url_lower for d in [
            "nytimes.com", "washingtonpost.com", "cnn.com", "foxnews.com",
            "politico.com", "thehill.com", "reuters.com", "apnews.com",
            "twitter.com", "x.com", "facebook.com", "instagram.com",
            "youtube.com", "bsky.app", "threads.net",
        ]):
            return True
    return False
