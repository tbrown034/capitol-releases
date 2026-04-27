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
    "blog",
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
    # Letter -- only the explicit "LETTER:" prefix and bare "Letter to ..."
    # title (where the page IS the letter). "Sheehy Leads Letter to ..." and
    # "Sends Letter to ..." were removed 2026-04-25 because they match the
    # press-release wrapper pattern -- titles announcing a letter, not the
    # letter itself. URL signal (/letters/, /letter-to-...) still classifies
    # genuine letter pages.
    (re.compile(r"^letter\s+to\b", re.I), "letter"),
]

# Press-release section URL markers. When the URL says the content lives
# in a press-release section, that wins over title heuristics -- a title
# like "Sheehy Leads Letter to..." on /press-releases/ is the press release
# announcing a letter, not the letter itself. (User rule, 2026-04-25.)
_PRESS_RELEASE_URL_MARKERS: tuple[str, ...] = (
    "/press-release",
    "/press_release",
    "/press-releases",
    "/newsroom/press",
    "/news/press",
)

# URL path patterns for non-press-release sections. Checked only when the
# URL is NOT in a press-release section.
_URL_RULES: list[tuple[str, str]] = [
    ("/op-ed", "op_ed"),
    ("/op_ed", "op_ed"),
    ("/commentary", "op_ed"),
    ("/floor-statement", "floor_statement"),
    ("/floor-speech", "floor_statement"),
    ("/speeches", "floor_statement"),
    ("/letters/", "letter"),
    ("/letter-to-", "letter"),
    ("/photo-release", "photo_release"),
    ("/presidential-actions/", "presidential_action"),
    ("/briefings-statements/", "statement"),
    # Newsletters / blogs / weekly columns. Some senators publish under
    # /newsletter/ (Curtis weekly), /weekly-column/ (Grassley), /diary/, etc.
    # Backfill_op_eds and backfill_wp_extras already map these by senator+CPT;
    # this lets the daily updater catch them too if they slip through silos.
    ("/newsletters/", "blog"),
    ("/newsletter/", "blog"),
    ("/weekly-column/", "blog"),
    ("/weekly-update/", "blog"),
    ("/diary/", "blog"),
    ("/blog/", "blog"),
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
    "blog": "blog",
    "blogs": "blog",
    "blog post": "blog",
    "blog posts": "blog",
    "newsletter": "blog",
    "newsletters": "blog",
    "weekly column": "blog",
    "weekly columns": "blog",
    "weekly update": "blog",
    "weekly updates": "blog",
}


def classify_content_type(
    title: str = "",
    url: str = "",
    categories: list[str] | None = None,
) -> str:
    """Classify a press release into a content type.

    Section-URL wins. A senator publishing on /press-releases/ is filing a
    press release, regardless of what the title says. Only when the URL
    explicitly carves out a different section (e.g. /letters/, /op-ed/) or
    is silent on section do title prefixes and WP categories take over.
    """
    url_lower = url.lower() if url else ""

    # 1. URL is explicitly a press-release section -- that wins.
    if url_lower and any(m in url_lower for m in _PRESS_RELEASE_URL_MARKERS):
        return "press_release"

    # 2. URL path rules for non-press-release sections.
    if url_lower:
        for path_fragment, content_type in _URL_RULES:
            if path_fragment in url_lower:
                return content_type

    # 3. Title prefix rules.
    if title:
        for pattern, content_type in _TITLE_RULES:
            if pattern.search(title):
                return content_type

    # 4. WordPress category tags.
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
