# RAG Learning Roadmap — "Ask the record"

*Started July 28, 2026. This file is the single source of truth for the guided RAG build. Update it at the end of every phase.*

## Product goal

A trustworthy "Ask the record" feature on individual member pages. It answers questions using only that member's archived official releases, with validated citations, honest abstention, and attribution framing ("the member's office said"). Trevor must be able to reproduce it, evaluate it, and defend every architectural decision in a technical interview.

## The four-part mental model

Every component of a RAG system does one of four jobs. Products and model names are replaceable choices underneath these responsibilities.

| Responsibility | Flow |
|---|---|
| **PREPARE** | Release → passages → embeddings → index |
| **FIND** | Question → query embedding → ranked passages |
| **ANSWER** | Question + retrieved evidence → cited answer |
| **CHECK** | Golden dataset + validation + traces → evidence of quality |

## Locked technology choices

| Job | Choice | Status |
|---|---|---|
| Canonical source database | Neon PostgreSQL | In use |
| Vector storage + similarity search | pgvector in Neon | Not yet introduced (Phase 4) |
| Embedding provider / model | OpenAI `text-embedding-3-small` | Not yet introduced (Phase 3) |
| Lexical retrieval | PostgreSQL full-text search | Exists in schema (`official_site_items.fts`) |
| Mature retrieval | Hybrid FTS + vector, only if evaluation supports it | Phase 5 decision |
| Observability | Langfuse (traces); Neon stays canonical for audit records | Phase 8 |
| Implementation style | Direct SDKs, explicit application logic. No LangChain / LlamaIndex / Pinecone in core | Standing |
| Generation model | Selected in Phase 6 via small evaluation (one recommended default) | Open |

Each choice gets an architecture decision record in `decisions/` when it becomes active.

## Phases

| # | Phase | Status |
|---|---|---|
| 0 | Reset and preserve | **Complete (2026-07-28)** |
| 1 | Product and evidence contract + first golden questions | **Complete (2026-07-29)** — golden-dataset.json; t1 relabel pending Trevor |
| 2 | Corpus inspection and chunking | **Complete (2026-07-29)** — sentence-aware; tariff-schedule hard-split fix |
| 3 | Embeddings and semantic similarity | **Complete (2026-07-29)** — sample verified; full backfill running (~$1.75) |
| 4 | pgvector storage and member-scoped retrieval | **Complete (2026-07-29)** — exact scan, halfvec, FTS fallback for unembedded |
| 5 | Retrieval baselines: FTS vs vector vs hybrid | **Complete (2026-07-29)** — vector adopted 5/5; hybrid REJECTED by eval (ADR-0004) |
| 6 | Constrained answer generation + model selection | **Complete (2026-07-29)** — search_result citations; haiku-4-5 by eval (ADR-0005) |
| 7 | Deterministic validation | **Complete (2026-07-29)** — status protocol + citation checks; cited_text check is containment, hardening TODO |
| 8 | Langfuse observability | **Deferred (deliberate scope cut)** — Neon ask_log carries traces/audit; Langfuse next |
| 9 | Production safeguards | **Partial** — rate limits, moderation bouncer, spend caps live; incremental embed of new releases TODO (daily cron hook) |
| 10 | Reproducibility and architecture review | Pending |
| 11 | Interview explanations | **Draft done** (interview-notes.md); polish in morning review |

**Compressed 2026-07-29 under the ADR-0001 revisit clause (interview deadline).
Everything above is locally verified only — production deploy (Phase E: commit,
push, Vercel env vars, smoke test) awaits Trevor's explicit go.**

## Research-locked design (2026-07-29, pre-build)

Three parallel research passes; full synthesis and verbatim reports in `research-2026-07-29.md`. Headlines: paragraph-packed ~800-token chunks with zero overlap and metadata headers; `halfvec(1536)` column; NO vector index tonight (exact member-scoped scan beats HNSW post-filter recall collapse at our per-member row counts); RRF for hybrid fusion, adoption still evidence-gated; Claude `search_result` content blocks with server-generated citations instead of the prototype's prompt markers; two-part abstention prompt with exact refusal wording; eval reported as raw counts at n=10.

## Completed verification

- Phase 0 (2026-07-28, locally verified): prototype removed; `git diff` empty on the four previously shared-edited files (`app/senators/[id]/page.tsx`, `app/house/[id]/page.tsx`, `package.json`, `pnpm-lock.yaml`); `pnpm build` compiled clean; 43 unrelated working-tree changes preserved untouched.

## Open risks and parked items

- **Neon table `ask_log` still exists** (2 test rows, created by the removed prototype). Left in place per instructions. Needs an explicit approve-to-drop decision; it may also be reusable as the audit table in later phases.
- The prototype snapshot lives in `.fallow/rag-prototype-snapshot-2026-07-28/` (gitignored, local only — it does not survive a fresh clone).
- Unrelated in-flight work shares the tree (Colorado collectors, `db/migrations/018_item_mentions.sql`, others). Every phase must re-inspect `git status` before editing.
- Embedding cost rule: no large paid embedding run without first estimating record count, token volume, and dollar cost. Archive is ~97,700 live records as of 2026-07-28.

## Exact next action

Say "proceed" to start Phase 1: define the product and evidence contract (what "Ask the record" answers, refuses, how it frames official claims, what a citation must prove) and draft the first human-reviewed golden questions. No RAG implementation in Phase 1.
