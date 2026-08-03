# Interview Notes

One entry per phase. Every claim is tagged: planned / locally verified / production verified. Never claim planned work as done.

---

## Phase 0 — Reset and preserve (2026-07-28) — locally verified

**What I did:** Removed a working autonomous RAG prototype from my codebase to rebuild it deliberately, with a recovery snapshot, surgical diff-scoped edits in a dirty tree, and build verification.

**Why it was needed:** I want to own every architectural decision. A feature I can't reproduce or defend has no interview value, however well it works.

**Alternatives considered:** Keep and study the prototype (teaches recognition, not reproduction); keep it as a baseline (anchors design to decisions I didn't make).

**How I tested it:** Per-file `git diff` before and after (empty on all shared files), `pnpm build` (clean compile), and confirmation that 43 unrelated working-tree changes survived untouched.

**What failed or changed:** Nothing failed. One surprise: the tree had grown with unrelated parallel work since the session began, which is why the removal was scoped from the live diff, not from memory.

**Interview-ready line:** "I actually deleted a working RAG prototype on my own project. It worked, but I couldn't defend its design decisions, so I rebuilt it in evaluated phases — contract first, then retrieval baselines measured against a golden dataset, then generation and validation. The rebuilt system I can walk you through end to end."

---
## Phases A-D — Build night (2026-07-29) — locally verified

**What I built:** End-to-end RAG on capitolreleases.com member pages: paragraph/sentence-aware chunking (147k passages from 103k releases), OpenAI embeddings in Neon pgvector (halfvec, no index — exact member-scoped scan), retrieval eval against a hand-labeled golden set, Claude generation with API-native search_result citations, a 5-status honesty protocol, deterministic server-side validation, moderation bouncer (fail-open), fire-and-forget audit logging, AI disclosure footer.

**Why:** Readers arrive with questions; search returns documents. Same pattern as Hearst's Kamala Harris News Assistant, on an archive I built and run myself.

**Alternatives I considered (each has an ADR):** Pinecone vs pgvector; HNSW index vs exact scan (exact won: post-filter recall collapse + our tiny per-member scopes); hybrid vs vector-only (EVAL DECIDED: vector 5/5 hit@5 vs hybrid 3/5 — fusion amplified my noisy lexical leg); prompt-marker citations vs API-native (native: server-generated receipts, validated by comparison to my own data); Sonnet vs Haiku for generation (parity on statuses, picked cheap+fast, validation is the safety net).

**How I tested it:** Golden dataset (5 answerable + 3 traps, labels I adjudicated); retrieval metrics as raw counts (recall@5, MRR); end-to-end status checks on two models; regression re-test after every prompt change.

**What failed or changed (the good stuff):**
1. White House tariff schedules broke the chunker — 78k chars, no sentences, periods only inside decimal codes -> one 19.5k-token chunk -> API 400. Fixed with a hard-splitter; 739 affected releases re-chunked.
2. Hybrid retrieval LOST to pure vector on my eval. I expected to ship hybrid; the numbers said no. Shipped vector-only, documented why.
3. My own trap label was wrong: labeled "abstain" using keyword-search evidence, but semantic retrieval found real 2028 material keyword search couldn't see. The model beat my eval — ground truth drafted with a lexical tool inherits its blind spots.

**30-second version:** "I run Capitol Releases, an archive of ~103,000 official statements from members of Congress that I scrape daily. Readers arrive with questions, but search returns documents. So I built Ask the Record: every member page has a question box that answers only from that member's archived releases, cites every claim to the source with the citation validated server-side, and — when the record can't answer — says so instead of guessing. I evaluated retrieval before trusting it: on my golden set, semantic search hit 5 for 5; the hybrid setup everyone recommends actually scored worse, so I shipped what measured best. It's the same pattern as your Kamala Harris News Assistant, on a corpus I built myself."

**Status tags:** build + evals = locally verified. Production deploy = NOT yet (pending commit/push/env approval). Never claim "in production" until Phase E completes.
## Production verification — July 30, 2026, 11:10 AM ET — PRODUCTION VERIFIED

Live on capitolreleases.com (deploy aliased ~11:07 AM):
- answered: Warren student loans -> 3 validated sources, 4.5s, verbatim quote (curl, prod)
- not_in_record: Durbin-re-Warren vibes trap refused correctly (curl, prod)
- no_sources: Jordan (sparse personal archive; his output goes to the committee site) declined honestly (curl, prod)
- Deploy-day fix worth telling: first prod deploy failed with 401s because the OpenAI key was stored WITH surrounding quotes (piped from a quoted .env.local line). The ask_log audit trail surfaced the exact error in one query — the observability layer debugged its own launch.

Claims now safe to make: "in production", "live on the site". Answer-quality evals at scale remain future work.
