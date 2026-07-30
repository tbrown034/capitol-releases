# ADR 0003: OpenAI text-embedding-3-small at native 1536 dims

*Status: accepted, active 2026-07-29.*

**Decision.** text-embedding-3-small for both document and query embeddings, native 1536 dimensions, metadata header prepended to each chunk.

**Context.** Document and query vectors must come from the same model family to be comparable. Corpus is ~87M tokens.

**Serious alternatives.** (1) text-embedding-3-large — better MTEB scores, 6.5x the price, larger vectors; overkill for a first measured baseline. (2) Open-weight models via Ollama (e.g. nomic-embed) — free and private, but adds serving infrastructure the one-night build doesn't need, and quality at this scale is unproven for us.

**Benefits.** $1.75 full-corpus cost; 2.5M tokens/min observed throughput; Matryoshka truncation available later.
**Costs/risks.** Provider dependency: re-embedding on a model change costs a full backfill (cheap here, but a real coupling). Embeddings cannot be reversed to text but do leak topic information — ours are public documents, so low sensitivity.
**Evidence.** Sample run: 5,135 chunks, $0.055, 65s; paraphrase retrieval verified ("college debt forgiveness" found student-loan releases with zero shared keywords).
**Revisit if.** Retrieval recall on a grown golden set shows systematic paraphrase misses, or embedding spend becomes material.
