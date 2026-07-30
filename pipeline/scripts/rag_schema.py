"""
Create the RAG passages table. Additive only — touches nothing existing.

rag_passages holds the PREPARE output: one row per chunk, carrying the
chunk text, its citable blocks, provenance back to the source release,
and (once embedded) the vector.

Design notes (research 2026-07-29, learning/rag/research-2026-07-29.md):
  - embedding column is halfvec(1536): half-precision floats, half the
    storage of vector(1536), no meaningful recall loss for similarity.
  - NO vector index: queries are always scoped to one member (100-2,500
    passages), where an exact scan has perfect recall and single-digit-ms
    cost. The btree on official_id drives the scan.
  - blocks jsonb stores the citable sentence-groups exactly as they will
    be sent to the model, so citation validation can compare by equality.
  - content_hash + chunk_version support incremental re-chunking later.

Idempotent. Run once:
    python -m pipeline.scripts.rag_schema
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2

_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_passages (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id        uuid NOT NULL,
  official_id    text NOT NULL,
  seq            integer NOT NULL,
  content        text NOT NULL,
  blocks         jsonb NOT NULL,
  char_count     integer NOT NULL,
  chunk_version  text NOT NULL DEFAULT 'v1',
  content_hash   text NOT NULL,
  embedding_model text,
  embedding      halfvec(1536),
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (item_id, seq, chunk_version)
);

CREATE INDEX IF NOT EXISTS rag_passages_official_idx ON rag_passages (official_id);
CREATE INDEX IF NOT EXISTS rag_passages_item_idx ON rag_passages (item_id);
"""


def main() -> None:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
            cur.execute("SELECT extversion FROM pg_extension WHERE extname='vector'")
            ver = cur.fetchone()
        conn.commit()
        print(f"rag_passages ready. pgvector version: {ver[0] if ver else 'MISSING'}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
