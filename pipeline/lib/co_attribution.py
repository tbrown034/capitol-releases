"""Attribute caucus-published releases to individual legislators.

Colorado publishes 100% of its legislative press output through four party
caucus organizations. The record's author is the caucus; the people in it
have to be recovered from the text. This module does that recovery.

Why not just read the title. The 2026-07-25 recon measured 239 Colorado
Senate Democrats releases from 2026: 25 (10.5%) name a sitting legislator
in the title, 236 (99.2%) name one in the body, mean 3.2 distinct
legislators per release, and only 19 (8%) name exactly one. Title-prefix
attribution -- the strategy the earlier state recon assumed -- would
misattribute roughly nine releases in ten.

So attribution is many-to-many and role-typed:

    primary    named in the headline
    quoted     carries a direct quotation attributed to them
    mentioned  named in the body without a quote

The distinction is the point. "Named in a release" is nearly meaningless
in a caucus corpus where bipartisan bill sponsors are listed by the dozen.
"Quoted in a release" is an editorial choice by the caucus press shop, and
it is the signal a reporter can actually use.

Determinism first, per CLAUDE.md. Every mention is produced by an explicit
rule and stores the literal matched string, so any attribution can be
traced to the words that caused it. No model is consulted in the write
path; `ambiguous_matches()` surfaces the residue a human (or an advisory
AI pass) should adjudicate.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

ROSTER_PATH = Path(__file__).resolve().parent.parent / "seeds" / "co_legislators_raw.json"

# Honorifics that can precede a surname in Colorado caucus copy. Order
# matters: the alternation is tried left to right, so longer leadership
# titles must precede the bare "Senator"/"Rep." forms or the short form
# wins and the leadership prefix is left dangling.
_TITLE_ALTERNATION = (
    r"(?:Senate\s+|House\s+)?(?:Majority|Minority)\s+Leader|"
    r"(?:Assistant|Deputy)\s+(?:Majority|Minority)\s+Leader|"
    r"President\s+Pro\s+Tem(?:pore)?|Speaker\s+Pro\s+Tem(?:pore)?|"
    r"Senate\s+President|Speaker|President|"
    r"Senator|Sen\.|Representative|Rep\.|Leader|Chair(?:woman|man|person)?"
)
_TITLE_PAT = re.compile(rf"(?:{_TITLE_ALTERNATION})\s*$", re.IGNORECASE)

# Chamber implied by an honorific, used to break surname collisions.
_SENATE_TITLES = re.compile(
    r"\b(?:senator|sen\.|senate\s+president|president\s+pro\s+tem)", re.IGNORECASE)
_HOUSE_TITLES = re.compile(
    r"\b(?:representative|rep\.|speaker)", re.IGNORECASE)

# Direct-quote attribution.
#
# The quotation mark has to sit ADJACENT to the attribution verb, not merely
# somewhere nearby. Colorado caucus releases are dense with both quotes and
# sponsorship lines, so a loose window match reads
#
#     "...safe by ..." Cosponsored by Senator Rod Pelton, R-Cheyenne Wells
#
# as a Pelton quote when the quote belongs to whoever spoke two sentences
# earlier. Verified against live Senate Democrats copy on 2026-07-28: the
# loose form produced false quotes on every "(Co)sponsored by ..." line.
#
# `by` and `from` are excluded from the verb list entirely -- in this corpus
# they introduce bill sponsorship, never speech.
_QUOTE_VERBS = r"said|says|added|stated|continued|concluded|noted|explained"

# Trailing form: `"...," said Senator Judy Amabile, D-Boulder.`
# Reading backwards from the name: title, verb, comma, closing quote.
#
# The title segment is matched as "a short run of capitalized tokens"
# rather than against the honorific list, because caucus copy stacks
# role labels the list will never fully enumerate -- `said JBC Chair
# Rep. Kipp` and `said JBC Vice Chair Sen. Bridges` both appear in the
# Joint Budget Committee releases. Anchoring on the quote mark plus the
# verb is what keeps this tight; the tokens after it only have to be
# permissive enough to step over the label.
# The verb is matched case-insensitively via an inline group; the token run
# after it stays case-SENSITIVE so it steps over role labels ("JBC Chair")
# without swallowing ordinary lowercase prose.
_TRAILING_ATTRIBUTION = re.compile(
    rf"[”\"]\s*,?\s*\b(?i:{_QUOTE_VERBS})\b\s+(?:[A-Z][\w.\-]*\s+){{0,5}}$")

# Leading form: `Senator Judy Amabile said, "..."` -- verb then an opening
# quote within a short span, no sentence break between them.
_LEADING_ATTRIBUTION = re.compile(
    rf"^\s*(?:,\s*[A-Z]?[^.\n]{{0,40}})?\s*\b(?:{_QUOTE_VERBS})\b[^.\n]{{0,20}}[“\"]",
    re.IGNORECASE)

_WINDOW = 140


@dataclass(frozen=True)
class Legislator:
    official_id: str
    full_name: str
    last_name: str
    chamber: str
    party: str
    district: int | None


@dataclass(frozen=True)
class Mention:
    official_id: str
    role: str           # primary | quoted | mentioned
    match_method: str   # title_match | quote_attribution | body_name
    matched_text: str
    confidence: float


def load_roster(path: Path = ROSTER_PATH) -> list[Legislator]:
    """Load the 100-seat Colorado General Assembly roster."""
    data = json.loads(Path(path).read_text())
    roster = []
    for m in data.get("members", []):
        roster.append(Legislator(
            official_id=m["official_id"],
            full_name=m["full_name"],
            last_name=m["last_name"],
            chamber=m.get("chamber") or "",
            party=m.get("party") or "",
            district=m.get("district"),
        ))
    return roster


class ColoradoAttributor:
    """Resolves legislator mentions in caucus release text.

    Build once and reuse -- the surname index and compiled patterns are
    shared across every release in a run.
    """

    def __init__(self, roster: list[Legislator] | None = None):
        self.roster = roster if roster is not None else load_roster()
        self._by_id = {m.official_id: m for m in self.roster}

        # Surnames shared by more than one sitting legislator cannot be
        # resolved from the surname alone. Colorado currently has two:
        # Stewart and Pelton. These are matched only when an honorific or a
        # full-name form disambiguates them.
        counts: dict[str, int] = {}
        for m in self.roster:
            counts[m.last_name.lower()] = counts.get(m.last_name.lower(), 0) + 1
        self.ambiguous_surnames = {s for s, n in counts.items() if n > 1}

        self._full_name_pats = [
            (m, re.compile(rf"\b{re.escape(m.full_name)}\b", re.IGNORECASE))
            for m in self.roster
        ]
        # One alternation over all surnames is far cheaper than 100 separate
        # scans per release, and releases can run several thousand words.
        surnames = sorted({m.last_name for m in self.roster}, key=len, reverse=True)
        self._surname_pat = re.compile(
            r"\b(" + "|".join(re.escape(s) for s in surnames) + r")\b")
        self._by_surname: dict[str, list[Legislator]] = {}
        for m in self.roster:
            self._by_surname.setdefault(m.last_name.lower(), []).append(m)

    def attribute(self, title: str, body_text: str) -> list[Mention]:
        """Return one mention per (legislator, role) found in a release.

        A legislator named in the headline is `primary`. One carrying a
        direct quote is `quoted`. Both can apply to the same person, and
        that is intentional -- the caucus both fronted them and quoted them.
        """
        mentions: dict[tuple[str, str], Mention] = {}

        for legislator, matched in self._find(title or ""):
            key = (legislator.official_id, "primary")
            mentions[key] = Mention(
                official_id=legislator.official_id,
                role="primary",
                match_method="title_match",
                matched_text=matched,
                confidence=1.0,
            )

        body = body_text or ""
        for legislator, matched, span in self._find_with_spans(body):
            quoted, evidence = self._is_quote_attribution(body, span)
            role = "quoted" if quoted else "mentioned"
            key = (legislator.official_id, role)
            if key in mentions:
                continue
            mentions[key] = Mention(
                official_id=legislator.official_id,
                role=role,
                match_method="quote_attribution" if quoted else "body_name",
                matched_text=evidence if quoted else matched,
                confidence=0.95 if quoted else 0.9,
            )

        # A legislator both quoted and merely mentioned elsewhere in the same
        # release is just quoted; the weaker row would double-count them in
        # every per-person total.
        for official_id in {k[0] for k in mentions if k[1] == "quoted"}:
            mentions.pop((official_id, "mentioned"), None)

        return list(mentions.values())

    def _find(self, text: str) -> list[tuple[Legislator, str]]:
        return [(m, matched) for m, matched, _ in self._find_with_spans(text)]

    def _find_with_spans(
        self, text: str
    ) -> list[tuple[Legislator, str, tuple[int, int]]]:
        """Locate every unambiguous legislator reference in `text`.

        Full-name matches are taken first and their spans suppress the
        surname pass, so "Javier Mabrey" is one match rather than a full
        name plus a redundant bare surname.
        """
        if not text:
            return []

        found: list[tuple[Legislator, str, tuple[int, int]]] = []
        consumed: list[tuple[int, int]] = []

        for legislator, pattern in self._full_name_pats:
            for match in pattern.finditer(text):
                found.append((legislator, match.group(0), match.span()))
                consumed.append(match.span())

        # Press copy introduces a person by full name and refers to them by
        # surname afterwards. So a shared surname later in the same document
        # resolves when exactly one of its claimants was already introduced
        # here -- which is how "said Stewart" becomes Sen. Stewart rather
        # than an unattributable guess between the two sitting Stewarts.
        introduced = {legislator.official_id for legislator, _, _ in found}

        for match in self._surname_pat.finditer(text):
            span = match.span()
            if any(start <= span[0] < end for start, end in consumed):
                continue
            surname = match.group(1).lower()
            candidates = self._by_surname.get(surname, [])
            if not candidates:
                continue

            preceding = text[max(0, span[0] - 40):span[0]]
            title_match = _TITLE_PAT.search(preceding)

            # Colorado copy drops the honorific on second reference and
            # attributes with a bare surname: `..." said Hamrick.` The
            # attribution verb plus an adjacent quote mark identifies a
            # person as reliably as a title does, so accept that too --
            # without it, the quotes in a release that front-loads its
            # honorifics are all missed.
            quote_context = bool(
                _TRAILING_ATTRIBUTION.search(text[max(0, span[0] - _WINDOW):span[0]])
                or _LEADING_ATTRIBUTION.search(text[span[1]:span[1] + _WINDOW])
            )

            if len(candidates) > 1:
                # Shared surname. Two things can resolve it: an honorific
                # that names a chamber, or a prior full-name reference in
                # this same document. Neither one means the mention is
                # dropped rather than guessed -- see ambiguous_matches().
                if title_match:
                    honorific = title_match.group(0)
                    if _SENATE_TITLES.search(honorific):
                        candidates = [c for c in candidates if c.chamber == "senate"]
                    elif _HOUSE_TITLES.search(honorific):
                        candidates = [c for c in candidates if c.chamber == "house"]
                    else:
                        candidates = [c for c in candidates if c.official_id in introduced]
                else:
                    candidates = [c for c in candidates if c.official_id in introduced]
                if len(candidates) != 1:
                    continue
            elif not title_match and not quote_context:
                # A bare surname with neither an honorific nor a quote
                # attribution is too weak on its own -- "Baisley" is a
                # legislator, but "Douglas" is a county and "Bird" is a bird.
                continue

            matched_text = (title_match.group(0) + " " if title_match else "") + match.group(1)
            found.append((candidates[0], matched_text.strip(), span))

        return found

    def _is_quote_attribution(self, text: str, span: tuple[int, int]) -> tuple[bool, str]:
        """True when the name at `span` is credited with a direct quotation.

        Both accepted forms require a quotation mark adjacent to the
        attribution verb. That adjacency is what separates a real quote
        from a paraphrase ("Sen. Smith said the bill was necessary") and
        from a sponsorship line that merely sits near someone else's quote.
        """
        after = text[span[1]:span[1] + _WINDOW]
        before = text[max(0, span[0] - _WINDOW):span[0]]

        if not (_TRAILING_ATTRIBUTION.search(before) or _LEADING_ATTRIBUTION.search(after)):
            return False, ""

        snippet = (before[-70:] + text[span[0]:span[1]] + after[:70]).strip()
        return True, re.sub(r"\s+", " ", snippet)

    def ambiguous_matches(self, text: str) -> list[str]:
        """Surnames skipped because they could not be resolved.

        Feeds the advisory review queue rather than the write path: these
        are the cases where a human or an AI adjudication pass adds value.
        """
        skipped = []
        for match in self._surname_pat.finditer(text or ""):
            surname = match.group(1).lower()
            if surname not in self.ambiguous_surnames:
                continue
            preceding = text[max(0, match.start() - 40):match.start()]
            if not _TITLE_PAT.search(preceding):
                skipped.append(match.group(1))
        return skipped
