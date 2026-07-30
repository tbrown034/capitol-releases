# How Capitol Releases Uses AI

*Last updated: July 28, 2026.*

Capitol Releases is an archive of official communications from elected officials: 100,000+ press releases, statements, and op-eds collected daily from official .gov sites, across the US Senate, US House, and a first wave of state officials. AI is used in three places. Everywhere else, the system is deterministic on purpose. The newest surface — a retrieval-augmented Q&A box on member pages — was built through a gated, evaluated process whose full decision log, golden dataset, and eval results are public in `learning/rag/`.

**The governing rule: AI assists, it does not drive.** Every database write is deterministic and traceable to a collector run. AI-generated text never enters the archive itself. It only summarizes or answers questions about records that already exist, and every AI output is validated against those records before anyone sees it.

---

## The AI surfaces

| Surface | Model | What it does | Guardrail |
|---|---|---|---|
| Daily and weekly brief | Claude Sonnet 4.6 | Axios-style editorial synthesis of the day's releases | Citation validator rejects the whole brief if any cited ID is not in the input set |
| Ask the record | Claude Haiku 4.5 + OpenAI text-embedding-3-small | Member-page Q&A grounded in that member's archived releases (RAG) | Server-validated citations; five-status honesty protocol; abstains rather than guesses |
| Post-collection validation | Claude Haiku 4.5 | Sanity-checks scraped records for classification and extraction errors | Advisory only — it can flag, it cannot write |

---

## 1. The brief: constrained generation with a hard citation gate

`pipeline/commands/brief.py` generates the daily brief. It is deliberately not agentic and not RAG — a single model call with deterministic inputs, so every brief is reproducible from its stored prompt hash.

**Inputs are assembled by SQL, not by the model.** The pipeline pulls the day's releases (active members, four content types, tombstoned records excluded), computes publishing volume against an eight-week same-day-of-week baseline, builds a "silent senators" list, and adds Senate calendar context (recess windows, scheduled votes). All of that goes into one prompt.

**Output is structured JSON.** Headline, lede, themed sections, signals — and every section must cite the `release_id`s it draws from.

**The gate:** a validator checks every cited ID against the input set. One unknown ID fails the run with a nonzero exit before any database write. A hallucinated citation cannot reach readers because the publish step never runs.

**Provenance:** every brief row stores `model_version`, `prompt_hash`, token counts, cost, the full source ID set, and the cited ID set. Regenerating a published brief retracts the old row with a reason rather than overwriting it — the same archival rule the press releases follow.

**The weekly brief is hierarchical summarization.** It reads the seven published daily briefs plus a title-only index of the week's releases, and its validator enforces citations against both layers. Dailies are the map step, the weekly is the reduce.

## 2. Ask the record: retrieval-augmented answers with validated citations

Every senator and House member page has an "Ask the record" box. Questions are answered only from that member's archived releases, with citations, or refused honestly.

**How retrieval works.** Releases are cut into ~800-token passages at sentence boundaries (most of this corpus has no paragraph breaks) and embedded with OpenAI `text-embedding-3-small` into a `pgvector` column in the same Postgres that holds the archive. A question is embedded the same way and compared against that member's passages only — the member boundary is enforced in SQL, never by the model. Retrieval is vector-only by measurement, not fashion: on the golden-question eval, semantic search hit 5/5 at top-5 while hybrid keyword+vector fusion scored 3/5 (`learning/rag/eval-results-2026-07-29.md`).

**How answering works.** Retrieved passages go to Claude as typed search-result blocks with the API's citation feature enabled, under a closed-book prompt. Answers return with machine-readable citations that the server validates against the exact passages it sent — invalid citations discard the whole answer. The model must declare one of five statuses: `answered`, `related_only` ("the record can't say how she voted, but here is what it shows"), `not_in_record`, `no_sources`, or `declined`. Saying "not in the record" is a designed outcome, not a failure.

**Accountability.** Every question is logged with its retrieval set, scores, citations, model versions, tokens, and outcome status — so hallucination-guard rejections are a queryable rate, not an anecdote. Questions pass a moderation screen (fail-open; the fail-closed walls are inside). Every answer carries a disclosure footer: AI-generated, not human-reviewed, verify before citing, with a correction link. Rate limits cap spend.

## 3. Post-collection validation: cheap AI as a smoke detector

After collection, `pipeline/lib/ai_validator.py` runs Claude Haiku 4.5 over samples of scraped records, checking for misclassified content types, extraction junk, and date anomalies. Its findings surface in internal quality reports. It has no write access — a deliberate ceiling, because a validator that can "fix" records is a validator that can corrupt them.

---

## Why these designs, in newsroom terms

The failure mode that matters for a news product is not "the AI wrote something awkward." It is "the AI attributed a position to an elected official that the official never took." Every design choice above flows from that.

**Grounding over knowledge.** The brief does not permit the model to use what it knows about a politician from training data. It sees only the day's releases, and the system prompt requires staying inside them rather than filling gaps.

**Validation over trust.** The generation surface has a deterministic checker between the model and the reader. The model is treated the way a newsroom treats a stringer: useful, fast, and fact-checked before publication.

**Provenance over polish.** Model version, prompt hash, source sets, cited sets, token counts, and cost are stored for every generation. Any published AI output can be traced to exactly which records produced it — the same standard the archive applies to scraped documents (`source_url`, `scrape_run`, `date_confidence`, deletion tombstones instead of hard deletes).

**Disclosure.** The brief page states the model that wrote it. This tracks the emerging consensus in newsroom AI guidance (AP's generative AI standards, the Paris Charter on AI and Journalism): label AI output, keep humans and verifiable sources in the loop, and never let generation substitute for the record.

**Scoped autonomy.** No agentic loops, no tool-calling, no AI-driven writes. Tool calling earns its place when a model must decide mid-task what to look up; the brief has fully determined inputs, so the simpler architecture is also the safer one.

## Honest gaps and the roadmap

An assessment is only credible if it lists what is missing.

- **No regression eval suite for the brief.** Citation validity is enforced mechanically, but tone, selection judgment, and summary accuracy are reviewed by a human, not scored against a golden set. A small eval harness (same day's releases, prompt variants, rubric scoring) is the next rigor step.
- **Citation validity is not quote validity.** The validator proves every citation points to a real source document; it does not yet machine-verify that quoted spans appear verbatim in that source. A substring check on quoted text is a planned, cheap addition.
- **Observability is first-party.** Structured logs and cost tracking exist in Postgres; dashboarding is ad hoc.

## What is deliberately not AI

Collection, parsing, classification, deduplication, date extraction, deletion detection, and every database write are deterministic Python. When a collector breaks, the fix is a selector change reviewed in a diff — not a prompt tweak. That boundary is the reason the archive can claim journalistic reliability while still shipping AI features on top of it.
