# ADR 0001: Remove the autonomous RAG prototype and rebuild through gated phases

*Status: accepted, 2026-07-28.*

**Decision.** Delete the working RAG prototype (built autonomously by Claude on 2026-07-28) and rebuild the feature through eleven gated learning phases, one at a time, with Trevor implementing understanding at each step.

**Context.** The prototype worked — locally verified with cited answers and guard paths — but Trevor could not have built it, evaluated it, or defended it in an interview. The project's primary purpose is portfolio and hiring credibility; a feature its author cannot explain is a liability in a technical interview, not an asset.

**Selected approach.** Full removal with a recoverable snapshot (`.fallow/rag-prototype-snapshot-2026-07-28/`), then a phased rebuild: contract → corpus → embeddings → pgvector → retrieval evaluation → generation → validation → observability → hardening → reproducibility → interview prep.

**Serious alternatives.**
1. *Keep the prototype and study it.* Faster to ship, but reading code teaches recognition, not reproduction. The interview goal requires the latter.
2. *Keep the prototype as the FTS baseline and build the vector path beside it.* Tempting, but it anchors the design to decisions Trevor didn't make and muddies "what did you build."

**Benefits.** Genuine ownership of every decision; a measured (not vibes-based) retrieval choice; durable artifacts that survive chat history.

**Costs and risks.** The feature ships later. Working code was deleted (mitigated by the snapshot). The learning cadence must be maintained or the roadmap goes stale.

**Evidence available.** Phase 0 verification: clean diffs on shared files, passing build, 43 unrelated changes preserved.

**Revisit if.** A hard deadline (e.g. an interview take-home or launch date) requires shipping the feature before the phases complete — in that case the snapshot can be restored as a stopgap, clearly labeled as prototype code.
