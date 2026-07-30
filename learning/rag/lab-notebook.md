# RAG Lab Notebook

Append-only. One entry per working session. Never rewrite prior entries.

---

## 2026-07-28 — Phase 0: Reset and preserve

**Question investigated:** Can the earlier autonomous RAG prototype be removed cleanly without disturbing unrelated in-flight work in a dirty tree?

**Hypothesis:** The prototype's footprint is fully separable: three new files, four hunks in two shared page files, one dependency, one doc's sections.

**Work performed:**
- Inventoried `git status --porcelain` and per-file diffs before touching anything.
- Snapshotted all prototype files plus the exact shared-file hunks to `.fallow/rag-prototype-snapshot-2026-07-28/`.
- Removed: `app/api/officials/[id]/ask/route.ts`, `app/components/ask-record.tsx`, `pipeline/scripts/create_ask_log.py`, `@anthropic-ai/sdk` dependency, four hunks in `app/senators/[id]/page.tsx` and `app/house/[id]/page.tsx`, the Ask row in `CLAUDE.md`, and the Ask sections of `AI.md`.
- Preserved: `AI.md`'s brief and validator documentation (separately requested work, not prototype), the devlog history, and all 43 unrelated working-tree changes.

**Evidence observed:** `git diff` on the four shared files is empty after removal. `pnpm build` compiled with zero errors, 37/37 pages generated. Unrelated changes (Colorado collectors, migration 018, seed files) untouched.

**Unexpected result:** The working tree had grown since the session snapshot — new unrelated files (`pipeline/collectors/co_caucus_collectors.py`, `db/migrations/018_item_mentions.sql`, others) appeared from parallel work. Reinforces the rule: inspect actual state, never trust a status snapshot.

**What we learned:** Diff-driven scoping works. Deciding "what is the prototype" from the live diff, not from memory of what was written, is what made surgical removal provable.

**What remains uncertain:** Fate of the Neon `ask_log` table (2 test rows) — parked, untouched, awaiting explicit approval. Whether `AI.md` should later fold into the public methodology page.

**Next experiment:** Phase 1 — write the evidence contract and first golden questions, before any retrieval code exists, so quality has a definition before the system does.

---
## 2026-07-29 — Pre-build research session

**Question investigated:** Is our compressed build plan aligned with mid-2026 best practice, or are we about to build 2023-era RAG?

**Hypothesis:** The broad shape (paragraph chunking, hybrid retrieval, deterministic validation) would hold, with parameter-level corrections.

**Work performed:** Three parallel research agents (chunking/embeddings, pgvector-on-Neon, eval/citations), each returning a sourced report. Corpus stats pulled locally to ground the chunking recommendation (median 650 tokens, p90 1,600, ~87M tokens total).

**Evidence observed:** See research-2026-07-29.md. Highest-impact findings: (1) chunk overlap is dead weight per Jan 2026 systematic study; (2) exact member-scoped vector scan beats an HNSW index at our query pattern — post-filter recall collapse plus a Neon HTTP-driver session-state trap make the index actively worse tonight; (3) the Claude API's search_result blocks with server-generated citations obsolete the prototype's [n]-marker + regex approach; (4) retrieved-context quality cliff near 2,500 tokens.

**Unexpected result:** The "obvious" architecture (HNSW index + prompt-marker citations) — what the deleted prototype and most 2024 tutorials would do — was wrong on both counts for our workload. Research before build paid for itself.

**What we learned:** Best practice is workload-dependent: per-member scoping (100-2,500 passages) changes the indexing answer entirely.

**What remains uncertain:** OpenAI rate tier (decides 17 vs 80 min backfill); TOAST storage behavior for halfvec rows (flagged, will measure); whether hybrid beats vector-only on OUR golden set — that stays an experiment.

**Next experiment:** Block 1 — evidence contract + 10 golden questions (7 answerable, 3 abstention traps), then chunker on a visual sample.

---
## 2026-07-29 (evening) — Phase A+B: chunker, passages table, first embeddings

**Question investigated:** Does semantic similarity actually beat keyword search on our corpus — and where does it fail?

**Work performed:** Built sentence-aware chunker (corpus forced it: 60% of bodies have no newlines; also strips nav junk and trailing "Print Email Share Tweet -30-" widgets caught during visual inspection). Created rag_passages (halfvec(1536), no vector index, btree on official_id; pgvector 0.8.0 confirmed on Neon). Chunked + embedded 3 members: 5,135 chunks, 2.74M tokens, $0.055, 65 seconds.

**Evidence observed:**
- Paraphrase win: "college debt forgiveness for borrowers" (no keyword overlap) retrieved Warren's student-debt Tax Bomb / student-aid / cancel-debt releases. This is the capability FTS cannot provide.
- Throughput: ~2.5M tokens/min on Trevor's OpenAI tier → full backfill ≈ 35 min, ~$1.75.
- THE VIBES TRAP, measured: "Durbin's personal opinion of Elizabeth Warren" returned confirmation-vote speeches at similarity 0.52-0.53 — nearly identical scores to genuinely relevant results in the good query (0.51-0.55). None mention Warren meaningfully.

**What we learned (the night's key lesson):** a similarity score is not a relevance judgment. 0.53 meant "exactly on topic" for one query and "same general vibe, useless" for another. Therefore: the floor-score gate can only catch true no-signal cases (calibrate LOW, ~0.35-0.4); the real defense against retrieved-but-irrelevant is the generation layer's abstention permission plus validation. "The prompt asks, the code enforces" — but here some judgments only the model can make, so the code enforces what it CAN (citations, scope) and the eval measures the rest.

**What remains uncertain:** whether hybrid beats vector-only on the golden set (Phase C eval); exact floor value (calibrate from golden traps).

**Next experiment:** full backfill (pending Trevor's go), then retrieval eval: FTS vs vector vs RRF hybrid on the 8 golden cases.

---
## 2026-07-29 (night) — Phases C+D: retrieval eval, generation, validation, three surprises

**Questions investigated:** Does hybrid beat vector on OUR corpus? Can the generation layer catch what the floor score can't? Which model should generate?

**Work performed:** Retrieval eval (FTS/vector/RRF on golden set); full backfill launched (failed, fixed, relaunched); production route v2 (search_result citations, 5-status protocol, deterministic validation, moderation bouncer fail-open, fire-and-forget ask_log); UI with disclosure footer; 2-model generation eval.

**Evidence observed:** see eval-results-2026-07-29.md.

**Three unexpected results:**
1. HYBRID LOST. Vector 5/5 hit@5 (MRR 0.74), hybrid 3/5 (0.63) — RRF's consensus reward amplified our noisy lexical leg. Shipped vector-only; the "mature" architecture stays parked until evidence supports it.
2. THE CORPUS BROKE THE CHUNKER. White House tariff schedules: 78k chars, zero sentence boundaries (all periods inside decimal codes like 2008.30.35) -> one 19.5k-token chunk -> OpenAI 400s. 739 items across 251 members had degenerate chunks. Fixes: hard-split for sentence-free text, per-input truncation guard, skip-don't-crash on BadRequest. Lesson: never assume prose.
3. THE MODEL BEAT THE EVAL. t1 trap ("Grassley 2028 presidential race", labeled abstain via FTS 0-hits) kept coming back related_only — because the record really does contain "Grassley 2028 Senate Run" chunks that only semantic search could see. Golden labels drafted with a lexical tool inherit that tool's blind spots. Trevor to relabel + add a genuinely-absent trap.

**Also confirmed:** t2 vibes trap passed end-to-end on both models (retrieval returned co-mention passages at 0.53 similarity; generation correctly refused). t3 related_only opening matched Trevor's ruling nearly verbatim. Prompt v2 tightened related_only; t3 regression-checked.

**Model decision:** haiku-4-5 default (parity on statuses, 5.7s vs ~9-13s, ~3x cheaper); ASK_MODEL env to swap. n=3 caveat recorded.

**What remains uncertain:** cited_text validation uses normalized containment, not strict equality (needs payload-shape confirmation before hardening); backfill completion; label rulings pending Trevor.

**Next experiment:** morning review with fresh eyes, then ship gate (commit, push, Vercel env), screenshots for the interview.

---
