"""
Retrieval evaluation: FTS vs vector vs hybrid (RRF) on the golden dataset.

The FIND step measured. For each answerable golden case we run three
retrieval methods and ask one question: did a chunk from a known-correct
release make the top k?

Methods:
  fts    — lexical: PostgreSQL full-text rank over chunk text, computed
           on the fly (member scope is <= ~2,500 chunks, no index needed)
  vector — semantic: cosine similarity between the question's embedding
           and each chunk's embedding, exact scan
  hybrid — Reciprocal Rank Fusion of both legs: each chunk scores
           sum(1/(60+rank)) across the two lists. Rank-based, so the
           incompatible score scales never need normalizing.

Metrics, reported as raw counts (n=5 answerable cases — smoke test, not
benchmark): hit@5, hit@10, and rank of first relevant chunk (for MRR).
Traps t1/t2 are also run to show what retrieval returns when the honest
answer is "nothing" — that calibrates the floor score.

Usage: python -m pipeline.scripts.rag_eval_retrieval
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

_repo_root = Path(__file__).resolve().parent.parent.parent
for _env_path in (_repo_root / "pipeline" / ".env", _repo_root / ".env.local"):
    if _env_path.exists():
        for line in _env_path.read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))

EMBED_MODEL = "text-embedding-3-small"
K = 10
RRF_K = 60


def embed_query(client, text: str) -> str:
    emb = client.embeddings.create(model=EMBED_MODEL, input=[text]).data[0].embedding
    return "[" + ",".join(f"{x:.5f}" for x in emb) + "]"


def run_fts(cur, official_id: str, question: str, k: int = K):
    cur.execute("""
        SELECT p.id::text, p.item_id::text,
               ts_rank(to_tsvector('english', p.content),
                       websearch_to_tsquery('english', %s)) AS score
        FROM rag_passages p
        WHERE p.official_id = %s
          AND to_tsvector('english', p.content) @@ websearch_to_tsquery('english', %s)
        ORDER BY score DESC LIMIT %s
    """, (question, official_id, question, k))
    return cur.fetchall()


def run_vector(cur, official_id: str, qvec: str, k: int = K):
    cur.execute("""
        SELECT p.id::text, p.item_id::text,
               1 - (p.embedding <=> %s::halfvec(1536)) AS score
        FROM rag_passages p
        WHERE p.official_id = %s AND p.embedding IS NOT NULL
        ORDER BY p.embedding <=> %s::halfvec(1536) LIMIT %s
    """, (qvec, official_id, qvec, k))
    return cur.fetchall()


def run_hybrid(cur, official_id: str, question: str, qvec: str, k: int = K):
    """RRF in SQL: per-leg LIMIT 40 (must exceed final k), fuse by rank."""
    cur.execute("""
        WITH lexical AS (
            SELECT p.id, p.item_id,
                   row_number() OVER (ORDER BY ts_rank(to_tsvector('english', p.content),
                                      websearch_to_tsquery('english', %s)) DESC) AS r
            FROM rag_passages p
            WHERE p.official_id = %s
              AND to_tsvector('english', p.content) @@ websearch_to_tsquery('english', %s)
            LIMIT 40
        ),
        semantic AS (
            SELECT p.id, p.item_id,
                   row_number() OVER (ORDER BY p.embedding <=> %s::halfvec(1536)) AS r
            FROM rag_passages p
            WHERE p.official_id = %s AND p.embedding IS NOT NULL
            ORDER BY p.embedding <=> %s::halfvec(1536)
            LIMIT 40
        )
        SELECT id::text, item_id::text, sum(1.0 / (%s + r)) AS score
        FROM (SELECT * FROM lexical UNION ALL SELECT * FROM semantic) legs
        GROUP BY id, item_id
        ORDER BY score DESC LIMIT %s
    """, (question, official_id, question, qvec, official_id, qvec, RRF_K, k))
    return cur.fetchall()


def first_hit_rank(rows, expected_item_ids: set[str]) -> int | None:
    for i, (_pid, item_id, _s) in enumerate(rows, start=1):
        if item_id in expected_item_ids:
            return i
    return None


def main() -> None:
    from openai import OpenAI
    client = OpenAI()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    golden = json.loads((_repo_root / "learning/rag/golden-dataset.json").read_text())
    answerable = [c for c in golden["cases"] if c.get("archive_can_answer") is True]
    traps = [c for c in golden["cases"] if c["id"] in ("t1", "t2")]

    methods = ("fts", "vector", "hybrid")
    tallies = {m: {"hit5": 0, "hit10": 0, "rr": []} for m in methods}

    print(f"{'case':4s} {'method':7s} {'first-hit rank':>14s}")
    for case in answerable:
        expected = {e["id"] for e in case["expected_release_ids"]}
        qvec = embed_query(client, case["question"])
        results = {
            "fts": run_fts(cur, case["member"], case["question"]),
            "vector": run_vector(cur, case["member"], qvec),
            "hybrid": run_hybrid(cur, case["member"], case["question"], qvec),
        }
        for m in methods:
            rank = first_hit_rank(results[m], expected)
            t = tallies[m]
            if rank is not None:
                t["rr"].append(1.0 / rank)
                if rank <= 5:
                    t["hit5"] += 1
                if rank <= 10:
                    t["hit10"] += 1
            else:
                t["rr"].append(0.0)
            print(f"{case['id']:4s} {m:7s} {str(rank) if rank else 'MISS':>14s}")

    n = len(answerable)
    print(f"\n=== summary over {n} answerable cases (raw counts) ===")
    print(f"{'method':7s} {'hit@5':>6s} {'hit@10':>7s} {'MRR':>6s}")
    for m in methods:
        t = tallies[m]
        mrr = sum(t["rr"]) / n
        print(f"{m:7s} {t['hit5']}/{n:>4} {t['hit10']}/{n:>5} {mrr:6.2f}")

    print("\n=== traps: top scores when the honest answer is 'nothing' ===")
    for case in traps:
        qvec = embed_query(client, case["question"])
        rows = run_vector(cur, case["member"], qvec, k=3)
        tops = ", ".join(f"{s:.3f}" for _, _, s in rows)
        print(f"{case['id']}: top vector similarities = {tops}")
    conn.close()


if __name__ == "__main__":
    main()
