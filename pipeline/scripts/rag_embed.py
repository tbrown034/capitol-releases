"""
Chunk releases into rag_passages and embed them with OpenAI.

PREPARE steps 2+3: passages -> embeddings -> index (the "index" here is
just the table itself — retrieval scans one member's rows exactly).

Two sub-steps, both idempotent and resumable:
  chunk: cut each release into chunks (pipeline/lib/rag_chunk.py) and
         insert rows. Re-running skips existing (item_id, seq) pairs.
  embed: find rows with no embedding yet, send their text to OpenAI in
         batches, store the returned vectors. Interrupt any time; rerun
         picks up where it left off.

What gets embedded is header + chunk text (see rag_chunk.embed_input):
the header keeps who/when/what attached to every fingerprint.

Cost control: --estimate prints chunk counts, token volume, and dollar
cost without spending anything. Never run --all without an estimate first.

Usage:
    python -m pipeline.scripts.rag_embed --members warren-elizabeth,grassley-chuck --estimate
    python -m pipeline.scripts.rag_embed --members warren-elizabeth,grassley-chuck
    python -m pipeline.scripts.rag_embed --all --estimate
    python -m pipeline.scripts.rag_embed --all          # senate first, then house, then rest
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from pipeline.lib.rag_chunk import chunk_release, embed_input  # noqa: E402

# pipeline/.env first (wins on conflicts), then root .env.local — the
# OPENAI_API_KEY lives in .env.local because the Next.js app needs it too.
_repo_root = Path(__file__).resolve().parent.parent.parent
for _env_path in (_repo_root / "pipeline" / ".env", _repo_root / ".env.local"):
    if _env_path.exists():
        for line in _env_path.read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))

MODEL = "text-embedding-3-small"
PRICE_PER_M_TOKENS = 0.02  # USD, verified 2026-07-29
MIN_BODY_CHARS = 200       # skip stub records
# One API request: stay well under 300k tokens and 2,048 inputs per request.
BATCH_CHAR_BUDGET = 800_000  # ~200k tokens
BATCH_MAX_INPUTS = 1_000


def member_order(cur, members: list[str] | None) -> list[str]:
    """Senate first so demo members embed early, then house, then the rest."""
    if members:
        return members
    cur.execute("""
        SELECT id FROM officials
        WHERE status = 'active'
        ORDER BY (chamber = 'senate' AND jurisdiction = 'us') DESC,
                 (chamber = 'house' AND jurisdiction = 'us') DESC,
                 id
    """)
    return [r[0] for r in cur.fetchall()]


def chunk_member(cur, official_id: str) -> int:
    cur.execute("""
        SELECT id, title, body_text FROM official_site_items
        WHERE official_id = %s AND deleted_at IS NULL
          AND body_text IS NOT NULL AND length(body_text) >= %s
    """, (official_id, MIN_BODY_CHARS))
    rows = cur.fetchall()
    values = []
    for item_id, title, body in rows:
        for c in chunk_release(title or "", body):
            values.append((item_id, official_id, c.seq, c.content,
                           json.dumps(c.blocks), len(c.content), c.content_hash))
    if values:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO rag_passages
              (item_id, official_id, seq, content, blocks, char_count, content_hash)
            VALUES %s
            ON CONFLICT (item_id, seq, chunk_version) DO NOTHING
        """, values)
    return len(values)


def pending_batches(cur, official_id: str):
    """Yield batches of (passage_id, text_to_embed) respecting request caps."""
    cur.execute("""
        SELECT p.id, s.full_name, s.party, s.state,
               pr.published_at::text, pr.title, p.content
        FROM rag_passages p
        JOIN official_site_items pr ON pr.id = p.item_id
        JOIN officials s ON s.id = p.official_id
        WHERE p.official_id = %s AND p.embedding IS NULL
        ORDER BY pr.published_at DESC NULLS LAST
    """, (official_id,))
    batch, chars = [], 0
    for pid, name, party, state, pub, title, content in cur.fetchall():
        text = embed_input(name, party, state, pub, title or "", content)
        if batch and (chars + len(text) > BATCH_CHAR_BUDGET or len(batch) >= BATCH_MAX_INPUTS):
            yield batch
            batch, chars = [], 0
        batch.append((str(pid), text))
        chars += len(text)
    if batch:
        yield batch


def embed_member(cur, conn, client, official_id: str) -> tuple[int, int]:
    done, tokens = 0, 0
    from openai import BadRequestError
    for batch in pending_batches(cur, official_id):
        # Belt and suspenders: no single input near the 8,192-token limit.
        texts = [t[:30_000] for _, t in batch]
        resp = None
        for attempt in range(6):
            try:
                resp = client.embeddings.create(model=MODEL, input=texts)
                break
            except BadRequestError as e:
                # Deterministic input problem — retrying is pointless. Skip
                # this batch (rows stay unembedded, visible in the estimate)
                # and keep going. Logged for repair, never silently dropped.
                print(f"    BAD BATCH skipped for {official_id}: {e}", flush=True)
                break
            except Exception as e:  # rate limit / transient — back off, retry
                wait = min(60, 10 * (attempt + 1))
                print(f"    embed error ({type(e).__name__}), retry in {wait}s", flush=True)
                time.sleep(wait)
        else:
            raise RuntimeError(f"embedding failed repeatedly for {official_id}")
        if resp is None:
            continue
        tokens += resp.usage.total_tokens
        vals = [
            (pid, "[" + ",".join(f"{x:.5f}" for x in d.embedding) + "]")
            for (pid, _), d in zip(batch, resp.data)
        ]
        psycopg2.extras.execute_values(cur, f"""
            UPDATE rag_passages AS p
            SET embedding = v.emb::halfvec(1536), embedding_model = '{MODEL}'
            FROM (VALUES %s) AS v(id, emb)
            WHERE p.id = v.id::uuid
        """, vals)
        conn.commit()
        done += len(vals)
    return done, tokens


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", help="comma-separated official_ids")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--estimate", action="store_true", help="price it, spend nothing")
    ap.add_argument("--embed-only", action="store_true",
                    help="skip the chunking pass (already chunked)")
    args = ap.parse_args()
    if not args.members and not args.all:
        ap.error("pass --members a,b,c or --all")

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    members = member_order(cur, args.members.split(",") if args.members else None)

    if not args.embed_only:
        print(f"[chunk] {len(members)} member(s)", flush=True)
        total_chunks = 0
        for m in members:
            n = chunk_member(cur, m)
            total_chunks += n
        conn.commit()
        print(f"[chunk] wrote/kept {total_chunks} chunk rows", flush=True)

    cur.execute("""
        SELECT count(*), coalesce(sum(char_count), 0) FROM rag_passages
        WHERE embedding IS NULL AND official_id = ANY(%s)
    """, (members,))
    n_pending, chars = cur.fetchone()
    est_tokens = int(chars / 4) + n_pending * 30  # +30 tokens/chunk for header
    cost = est_tokens / 1_000_000 * PRICE_PER_M_TOKENS
    print(f"[estimate] {n_pending:,} chunks pending, ~{est_tokens:,} tokens, ~${cost:.2f}")
    if args.estimate:
        conn.close()
        return

    from openai import OpenAI
    client = OpenAI()
    t0 = time.time()
    done_total, tok_total = 0, 0
    for i, m in enumerate(members):
        done, tok = embed_member(cur, conn, client, m)
        done_total += done
        tok_total += tok
        if done:
            rate = done_total / max(1, time.time() - t0)
            print(f"  [{i+1}/{len(members)}] {m}: +{done} chunks "
                  f"({done_total:,} total, {rate:.0f} chunks/s)", flush=True)
    cost = tok_total / 1_000_000 * PRICE_PER_M_TOKENS
    print(f"[done] {done_total:,} chunks embedded, {tok_total:,} tokens, "
          f"${cost:.3f}, {time.time()-t0:.0f}s")
    conn.close()


if __name__ == "__main__":
    main()
