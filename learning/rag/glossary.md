# RAG Glossary

Plain-language definitions with a Capitol Releases example. Concepts are added only when we reach them in the build.

---

**RAG (retrieval-augmented generation).** Answering a question by first fetching relevant documents, then having a model write an answer grounded only in what was fetched. The model is a writer working from a folder of clippings you handed it, not from memory. *Capitol Releases example: "What has Warren said about student loans?" → fetch her releases that mention student loans → write a cited summary from only those.*

**PREPARE.** Everything done to documents before anyone asks a question: splitting releases into passages, computing embeddings, indexing. *Example: turning a 12-paragraph Warren release into retrievable passages.*

**FIND.** Turning a question into a ranked list of relevant passages. *Example: matching "student loan debt" against Warren's archive and returning the eight best passages.*

**ANSWER.** Generating a cited response from the question plus the retrieved passages, and nothing else. *Example: two paragraphs with [1][2] markers pointing at specific releases.*

**CHECK.** Proving quality with evidence: a golden dataset of questions with known-correct sources, deterministic validation of citations, and traces of every step. *Example: knowing that for 20 test questions, the right release appeared in the top 5 results 18 times.*

---
**Embedding.** A list of 1,536 numbers that acts as a fingerprint of a text's meaning; similar meanings get similar fingerprints regardless of shared words. *Example: "college debt forgiveness" retrieved Warren's student-loan releases with zero keyword overlap.*

**Cosine similarity.** The closeness score between two fingerprints, here roughly 0 to 1. Crucial lesson from our traps: there is no absolute "good" score — irrelevant passages scored 0.53-0.66, the same band as correct ones. Scores rank; they do not judge.

**halfvec.** Storing each fingerprint number at half precision — half the disk space, same search results. Millimeters instead of micrometers when you only need to know which city is closer.

**Recall@k.** "Was a correct passage in the top k results?" Our headline retrieval metric, reported as raw counts (5/5) never percentages at this sample size.

**MRR (mean reciprocal rank).** How high the first correct result lands, averaged: rank 1 = 1.0, rank 2 = 0.5. Rewards putting the right passage first, not just somewhere in the list.

**RRF (reciprocal rank fusion).** Merging two ranked lists by rank position instead of raw scores. Punchline from our eval: fusion rewards consensus, so a noisy list can drag down a good one — hybrid lost to pure vector here.

**search_result citations.** The Claude API feature where we pass passages as typed blocks and the answer comes back with machine-readable receipts (which passage, which exact quoted text) attached to each sentence. Replaces trusting the model to format [1] markers.

**The five statuses.** answered / related_only / not_in_record / no_sources / declined. related_only is Trevor's addition: "we can't tell you how she voted, but here's what the record shows" — answer the answerable part, flag the rest.

**Retrieved-but-irrelevant.** RAG's signature failure: retrieval always returns the nearest passages even when nothing is truly relevant. Caught not by score floors but by giving the generation layer explicit permission to refuse — and validating it.
