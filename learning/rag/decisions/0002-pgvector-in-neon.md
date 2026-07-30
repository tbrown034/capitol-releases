# ADR 0002: pgvector in Neon for vector storage and similarity search

*Status: accepted, active 2026-07-29.*

**Decision.** Store passage embeddings in a `halfvec(1536)` column in the existing Neon Postgres, searched with pgvector's cosine operator. No separate vector database.

**Context.** The archive already lives in Neon; queries are always scoped to one member (100-2,500 passages); the app already speaks Postgres through one driver.

**Selected approach.** Single rag_passages table; exact member-scoped scan (no vector index); btree on official_id. pgvector 0.8.0 verified on Neon.

**Serious alternatives.** (1) Pinecone — managed scaling and integrated retrieval APIs, but a second system to sync, secure, and pay for, and our joins (passages -> releases -> officials) are native SQL here. Documented as the primary alternative per the learning plan; revisit at corpus-wide search scale. (2) HNSW index inside pgvector — the default advice, but measured reality: with member filters, approximate indexes suffer post-filter recall collapse, and the Neon HTTP driver can't hold the session settings that fix it. Exact scan at our per-member row counts is both simpler and more accurate.

**Benefits.** One database, one backup story, relational joins, provenance in the same rows.
**Costs/risks.** Corpus-wide semantic search would need the HNSW path (documented params: m=16, ef_construction=64). TOAST fetch overhead flagged but unmeasured.
**Evidence.** Retrieval eval 2026-07-29: vector 5/5 hit@5 with exact scan; sub-second query latency in dev.
**Revisit if.** Cross-member search ships, per-member passage counts grow 10x, or p95 retrieval latency degrades in production.
