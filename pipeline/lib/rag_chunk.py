"""
Turn one press release into retrieval passages ("chunks").

This is the PREPARE step of the RAG pipeline: release -> passages.

Corpus reality (measured 2026-07-29, see learning/rag/lab-notebook.md):
only ~6% of bodies contain blank-line paragraphs and ~60% contain no
newlines at all, so the primary split boundary here is the SENTENCE, not
the paragraph. Where real paragraph breaks exist we respect them.

Structure produced:
  - A "block" is a group of a few sentences (~700 chars). Blocks are the
    citable unit: each block becomes its own text block inside the
    search_result we send to the model, so citations land at block level.
  - A "chunk" is a group of blocks (~3,200 chars ~= 800 tokens). Chunks are
    the retrieval unit: each chunk gets exactly one embedding.

Sizing follows the 2026-07-29 research synthesis: ~800-token chunks,
zero overlap, budgeted in characters at ~4 chars per token.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# Chunk sizing (characters; ~4 chars per token)
BLOCK_TARGET = 700
BLOCK_CAP = 1400
CHUNK_TARGET = 3200
CHUNK_CAP = 4200

# Leading "July 28, 2026" style date lines that some CMSes prepend to the body.
_DATE_PREFIX = re.compile(
    r"^\s*(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4}\s*"
)

# Trailing share-widget boilerplate some CMSes append after the story
# ("-30-", "###", "Print Email Share Tweet", ...). Stripped so it is never
# embedded or cited. "-30-" is the old wire-copy end-of-story mark.
_TRAIL_JUNK = re.compile(
    r"(?:\s*(?:-30-|###|Print|Email|Share|Tweet|Facebook|Twitter|"
    r"Read the full text here\s*\.?|Permalink:?))+\s*$",
    re.IGNORECASE,
)

# Sentence boundary: after . ! ? (optionally a closing quote), before a
# capital letter or opening quote. Negative lookbehinds guard the most
# common abbreviations in congressional press copy.
_SENT_SPLIT = re.compile(
    r"(?<!U\.S\.)(?<!D\.C\.)(?<!Mr\.)(?<!Ms\.)(?<!Mrs\.)(?<!Dr\.)"
    r"(?<!Sen\.)(?<!Rep\.)(?<!Sens\.)(?<!Reps\.)(?<!Gov\.)(?<!Lt\.)"
    r"(?<!Gen\.)(?<!Col\.)(?<!Sgt\.)(?<!Jr\.)(?<!Sr\.)(?<!No\.)(?<!H\.R\.)"
    r"(?<=[.!?”\"])\s+(?=[A-Z“\"(])"
)


def clean_body(title: str, body: str) -> str:
    """Strip the junk some collectors leave at the top of body_text.

    Three known artifacts, in order: site-navigation junk ("Skip to
    primary navigation ..."), a prepended date line, and a duplicate of
    the title. Everything else passes through untouched.
    """
    text = (body or "").strip()
    if text.lower().startswith("skip to"):
        # Navigation junk (0.3% of corpus). Recover by jumping to the first
        # occurrence of the title, or failing that the WASHINGTON dateline.
        probe = (title or "")[:60].lower()
        idx = text.lower().find(probe) if probe else -1
        if idx <= 0:
            idx = text.find("WASHINGTON")
        if idx > 0:
            text = text[idx:]
    text = _DATE_PREFIX.sub("", text)
    tclean = (title or "").strip()
    if tclean and text.lower().startswith(tclean.lower()):
        text = text[len(tclean):].lstrip(" –—-:.\n")
    text = _TRAIL_JUNK.sub("", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def _hard_split(unit: str, cap: int) -> list[str]:
    """Last resort for degenerate text with no sentence boundaries at all
    (e.g. White House tariff schedules: 78k chars of "0801.21.00 Brazil
    nuts in shell" where every period sits inside a decimal code). Splits
    at the last whitespace before the cap so no token is cut in half.
    """
    out = []
    while len(unit) > cap:
        cut = unit.rfind(" ", cap // 2, cap)
        if cut == -1:
            cut = cap
        out.append(unit[:cut].strip())
        unit = unit[cut:].strip()
    if unit:
        out.append(unit)
    return out


def _pack(units: list[str], target: int, cap: int, sep: str) -> list[str]:
    """Greedy packer: fill a group until target, never exceed cap.

    Units longer than cap are hard-split first — a lesson from the corpus:
    never assume prose. Sentence-free documents exist and must still obey
    the embedding API's per-input token limit.
    """
    units = [piece for u in units for piece in
             (_hard_split(u, cap) if len(u) > cap else [u])]
    groups: list[list[str]] = []
    cur: list[str] = []
    cur_len = 0
    for u in units:
        ulen = len(u) + len(sep)
        if cur and cur_len + ulen > cap:
            groups.append(cur)
            cur, cur_len = [], 0
        cur.append(u)
        cur_len += ulen
        if cur_len >= target:
            groups.append(cur)
            cur, cur_len = [], 0
    if cur:
        groups.append(cur)
    return [sep.join(g) for g in groups]


@dataclass
class Chunk:
    seq: int
    blocks: list[str]  # citable units, sent as separate text blocks

    @property
    def content(self) -> str:
        return "\n\n".join(self.blocks)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


def chunk_release(title: str, body: str) -> list[Chunk]:
    """Release text -> list of chunks, each made of sentence-group blocks."""
    text = clean_body(title, body)
    if not text:
        return []

    # Respect real paragraphs where they exist; fall back to sentences.
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    blocks: list[str] = []
    for para in paragraphs if len(paragraphs) > 1 else [text]:
        if len(para) <= BLOCK_CAP:
            blocks.append(re.sub(r"\s+", " ", para))
        else:
            blocks.extend(_pack(split_sentences(re.sub(r"\s+", " ", para)),
                                BLOCK_TARGET, BLOCK_CAP, " "))

    packed = _pack(blocks, CHUNK_TARGET, CHUNK_CAP, "\n\n")
    # Drop confetti: chunks under 40 chars carry no meaning worth retrieving.
    return [Chunk(seq=i, blocks=p.split("\n\n"))
            for i, p in enumerate(p for p in packed if len(p) >= 40)]


def embed_input(member_name: str, party: str, state: str,
                date_iso: str | None, title: str, chunk_content: str) -> str:
    """The text that actually gets embedded: metadata header + chunk body.

    The header keeps who/when/what attached to every chunk so a passage
    still carries its context when retrieved alone (measured retrieval win,
    research 2026-07-29).
    """
    date_part = date_iso[:10] if date_iso else "date unknown"
    header = f"{member_name} ({party}-{state}) | {date_part} | {title}"
    return f"{header}\n{chunk_content}"
