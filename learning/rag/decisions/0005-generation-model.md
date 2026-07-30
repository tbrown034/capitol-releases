# ADR 0005: claude-haiku-4-5 as the production generation model

*Status: accepted, active 2026-07-29.*

**Decision.** Haiku 4.5 default for answer generation; ASK_MODEL env swaps without deploy.

**Context.** Locked rule: pick via small evaluation, recommend one default. Compared claude-sonnet-4-6 vs claude-haiku-4-5 on golden cases end-to-end.

**Evidence.** Status parity on every tested case including both traps (t2 vibes trap refused correctly on both; t3 produced Trevor's related_only shape on both). Haiku: 5.7s and ~1/3 the token price; Sonnet: ~9-13s, slightly richer prose on the answered case.

**Why the cheap model is safe here.** The trust layer is architectural, not model-dependent: closed-book search_result context, server-validated citations, status protocol, member scope in SQL. A weaker model fails into visible validation errors, not silent fabrication.

**Serious alternatives.** (1) Sonnet 4.6 — marginally better synthesis, 3x cost, slower; the right upgrade if answer-quality evals ever show a gap. (2) Opus-tier — unjustified by any observed failure.
**Costs/risks.** n=3 comparison; quote-fidelity differences may appear at volume (watched via ask_log validation_failed rate).
**Revisit if.** validation_failed or unfaithful-answer rate exceeds a few percent, or a grown golden set shows quality gaps.
