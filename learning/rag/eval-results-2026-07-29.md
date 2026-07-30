# Eval results — July 29, 2026

Raw counts throughout: n is tiny, this is a smoke test with teeth, not a benchmark.

## Retrieval eval (5 answerable golden cases, 3 members, chunk-level)

Question: did a chunk from a known-correct release appear in the top k?

| method | hit@5 | hit@10 | MRR | notes |
|---|---|---|---|---|
| FTS (lexical) | 4/5 | 4/5 | 0.45 | missed g3 entirely (farm bill Q&A) |
| **vector (adopted)** | **5/5** | **5/5** | **0.74** | first-hit rank 1 on 3 of 5 cases |
| hybrid RRF | 3/5 | 4/5 | 0.63 | lost g5 from top 10 entirely |

**Decision: vector-only for v1.** The surprise: hybrid RRF *underperformed* pure vector. Mechanism: RRF rewards consensus between legs; our lexical leg is noisy, so chunks that appeared mid-list in BOTH legs outranked chunks that were top-ranked in the good (vector) leg alone. The locked plan said "hybrid only if evaluation supports it" — it did not. Hybrid stays on the roadmap pending a better lexical leg (title boosting, phrase queries) and a bigger golden set.

## Trap analysis (what similarity scores mean — nothing absolute)

| trap | top vector similarities | outcome |
|---|---|---|
| t1 (Grassley 2028) | 0.657 / 0.625 / 0.605 | see reversal below |
| t2 (Durbin re: Warren) | 0.534 / 0.529 / 0.522 | correctly refused |

Irrelevant passages score in the same 0.5-0.66 band as genuinely relevant ones.
A similarity floor cannot judge relevance; it only detects total absence of
signal. Floor set to 0.30; relevance judgment belongs to the generation layer
+ validation.

## The t1 ground-truth reversal (best lesson of the night)

t1 was labeled "abstain — FTS found 0 matching releases." End-to-end, the model
kept answering `related_only`. Inspection of the retrieved chunks showed the
record **does** contain 2028 material: "Grassley 2028 Senate Run" in a Capitol
Hill Report. Keyword search couldn't see it (no "presidential race" tokens);
semantic search could. **The golden label was biased by the lexical tool used
to draft it — the model outperformed the eval.** Pending Trevor's ruling:
relabel t1 (related_only acceptable) and add a genuinely-absent replacement trap.

## End-to-end status checks (local dev, both models)

| case | expected | sonnet-4-6 | haiku-4-5 |
|---|---|---|---|
| g1 student loans | answered + citations | answered, per-quote citations | answered, 3 sources, 5.7s |
| t2 vibes trap | not_in_record | not_in_record | not_in_record |
| t3 NDAA vote | related_only (Trevor's ruling) | related_only, correct opening | related_only, correct opening |
| t1 2028 | (label under review) | related_only | — |

**Generation model decision: claude-haiku-4-5 default** (status parity on all
tested cases, ~40% faster, ~3x cheaper; deterministic validation is the safety
net). `ASK_MODEL` env var swaps models without a deploy. Honest caveat: n=3
comparison; revisit with the full golden set + answer-quality rubric.

## Prompt iteration log

- v1 related_only definition let the model stretch topically-adjacent material.
  Tightened to: specific-fact-missing on a substantively-covered subject only.
  t3 stayed correct after tightening (regression-checked). t1 stayed
  related_only — which inspection then justified (see reversal above).
