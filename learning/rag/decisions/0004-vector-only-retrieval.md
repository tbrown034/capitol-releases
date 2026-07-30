# ADR 0004: Vector-only retrieval for v1 — hybrid rejected by evidence

*Status: accepted, active 2026-07-29. This reverses the expected outcome.*

**Decision.** Ship member-scoped vector retrieval alone. Do not fuse with full-text search yet.

**Context.** The locked plan intended hybrid FTS+vector "only if evaluation supports it." The eval said no: vector 5/5 hit@5 (MRR 0.74), FTS 4/5 (0.45), hybrid RRF 3/5 (0.63).

**Why hybrid lost.** RRF rewards consensus between lists. Our lexical leg is noisy (question words like "said" match everywhere; chunk-level tsvectors are computed without title context), so passages mediocre in both lists outranked passages excellent in one. Fusion amplifies a weak leg's noise.

**Serious alternatives.** (1) Weighted score fusion — worse than RRF for incompatible score scales. (2) Better lexical leg first (title boost, phrase matching) then re-fuse — the actual roadmap item.

**Benefits.** Simpler query path; measured superiority on our golden set; honest "the numbers decided" story.
**Costs/risks.** n=5. Lexical wins on exact identifiers (bill numbers, names) are real; some future question type will miss. FTS fallback still serves unembedded members.
**Evidence.** learning/rag/eval-results-2026-07-29.md.
**Revisit if.** Golden set reaches ~25+ cases including bill-number/name queries, or ask_log shows misses hybrid would catch.
