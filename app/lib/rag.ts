import OpenAI from "openai";
import { sql } from "./db";

// FIND: question -> query embedding -> ranked passages, scoped to one member.
//
// Retrieval is vector-only, an evidence-based choice: on the 2026-07-29
// golden-set eval, vector search hit 5/5 answerable cases in the top 5
// (MRR 0.74) while hybrid RRF fusion with our noisy lexical leg scored
// worse (3/5). See learning/rag/eval-results. Members whose passages are
// not yet embedded fall back to full-text search so every page works.
//
// The floor score (0.30) only catches "no signal at all". It cannot catch
// retrieved-but-irrelevant: on trap questions, irrelevant passages scored
// 0.52-0.66 — the same range as genuinely relevant ones. Judging relevance
// is the generation layer's job (with abstention permission); the floor is
// just the cheap outer wall.

export const EMBED_MODEL = "text-embedding-3-small";
// Calibrated 2026-07-30 on live traffic: one-word queries ("housing") top
// out near 0.30 while full questions reach 0.5+, so 0.30 wrongly refused
// short queries. The floor only screens total absence of signal; judging
// relevance is the generation layer's job.
export const SCORE_FLOOR = 0.15;
const CANDIDATES = 12;
// Retrieved-context budget: quality degrades past ~2,500 tokens of context
// (research 2026-07-29), so we stop adding passages at ~10k chars.
const CONTEXT_CHAR_BUDGET = 10_000;
const MAX_PASSAGES = 6;

export type RetrievedPassage = {
  id: string;
  item_id: string;
  title: string;
  source_url: string;
  published_at: string | null;
  blocks: string[];
  score: number;
};

export type RetrievalResult = {
  passages: RetrievedPassage[];
  method: "vector" | "fts_fallback";
  topScore: number | null;
};

export async function embedQuery(question: string): Promise<string> {
  const openai = new OpenAI();
  const resp = await openai.embeddings.create({
    model: EMBED_MODEL,
    input: [question],
  });
  return "[" + resp.data[0].embedding.map((x) => x.toFixed(5)).join(",") + "]";
}

type Row = {
  id: string;
  item_id: string;
  title: string;
  source_url: string;
  published_at: string | null;
  blocks: string[];
  score: number;
};

function budgeted(rows: Row[]): RetrievedPassage[] {
  const out: RetrievedPassage[] = [];
  let chars = 0;
  for (const r of rows) {
    const len = r.blocks.join(" ").length;
    if (out.length > 0 && (chars + len > CONTEXT_CHAR_BUDGET || out.length >= MAX_PASSAGES)) {
      break;
    }
    out.push(r);
    chars += len;
  }
  return out;
}

export async function retrieve(
  officialId: string,
  question: string,
): Promise<RetrievalResult> {
  const qvec = await embedQuery(question);
  const rows = (await sql`
    SELECT p.id::text AS id, p.item_id::text AS item_id,
           pr.title, pr.source_url, pr.published_at::text AS published_at,
           p.blocks,
           1 - (p.embedding <=> ${qvec}::halfvec(1536)) AS score
    FROM rag_passages p
    JOIN official_site_items pr ON pr.id = p.item_id
    WHERE p.official_id = ${officialId}
      AND p.embedding IS NOT NULL
      AND pr.deleted_at IS NULL
    ORDER BY p.embedding <=> ${qvec}::halfvec(1536)
    LIMIT ${CANDIDATES}
  `) as Row[];

  if (rows.length > 0) {
    const above = rows.filter((r) => r.score >= SCORE_FLOOR);
    return {
      passages: budgeted(above),
      method: "vector",
      topScore: rows[0]?.score ?? null,
    };
  }

  // Member not embedded yet (backfill in progress): lexical fallback so the
  // feature degrades honestly instead of going dark.
  const ftsRows = (await sql`
    SELECT p.id::text AS id, p.item_id::text AS item_id,
           pr.title, pr.source_url, pr.published_at::text AS published_at,
           p.blocks,
           ts_rank(to_tsvector('english', p.content),
                   websearch_to_tsquery('english', ${question}))::float AS score
    FROM rag_passages p
    JOIN official_site_items pr ON pr.id = p.item_id
    WHERE p.official_id = ${officialId}
      AND pr.deleted_at IS NULL
      AND to_tsvector('english', p.content) @@ websearch_to_tsquery('english', ${question})
    ORDER BY score DESC
    LIMIT ${CANDIDATES}
  `) as Row[];

  return {
    passages: budgeted(ftsRows),
    method: "fts_fallback",
    topScore: ftsRows[0]?.score ?? null,
  };
}
