# Capitol Releases

A journalism and public-records project building the canonical "on the record" archive for U.S. elected officials: every original press release, statement, op-ed, floor speech, and social post, collected daily with full provenance.

Live at **[capitolreleases.com](https://capitolreleases.com)**.

## Coverage

Numbers below are from the production database, 2026-08-03.

| Corpus | Size |
|--------|------|
| Site releases (live records) | 104,079 |
| U.S. senators covered | 100 |
| U.S. House members covered | 435 |
| State and executive officials (beta) | 257 |
| Bluesky posts | 18,678 |
| Senate floor speeches (Congressional Record) | 5,676 |
| Published daily and weekly briefs | 70 |

Coverage starts January 1, 2025 for Congress. Every record carries provenance — source URL, scrape run, date source, date confidence — and deletions at the source become tombstones, never removals.

## Product surfaces

- **Feed, search, trending** — full-text search across the corpus with per-chamber and per-type filters.
- **Member pages** — per-official archive, release-volume analytics, and **Ask the record**: retrieval-augmented Q&A grounded in that member's collected releases, with server-validated citations and a disclosure footer. Vector retrieval over pgvector (OpenAI text-embedding-3-small), answers from Claude (`ASK_MODEL`, default Haiku 4.5); an answer that cites outside its retrieval set is discarded, not repaired.
- **Daily brief** (`/brief`) — AI-drafted summary of the day's releases, one Claude Sonnet call per edition, every claim cited back to source records. A weekly recap publishes on the same surface.
- **Social** (`/social`) — verified-handle Bluesky archive, kept separate from the press-release feed.
- **Floor speeches** (`/speeches`) — per-speaker segments from the daily Congressional Record.
- **State tier (beta)** — first state jurisdictions live, including Texas surfaces (`/texas`) and the Colorado caucus-pressroom model.
- **Admin** (`/admin`) — run history, health checks, open alerts. Google OAuth via better-auth; admin identity comes from `ADMIN_EMAIL`.

## Repository layout

| Path | Purpose |
|------|---------|
| `app/` | Next.js 16 frontend (App Router, React 19, Tailwind 4, D3) |
| `pipeline/` | Python collection pipeline: collectors, CLI, tests, repair scripts |
| `pipeline/seeds/` | Per-source config: URL, CMS family, selectors, collection method |
| `db/` | Postgres schema and migrations |
| `learning/rag/` | RAG build log: ADRs, eval results, golden dataset |
| `.github/workflows/` | CI gate plus daily/weekly cron pipelines |

## Stack

- **Frontend** — Next.js 16, React 19, Tailwind 4, TypeScript, D3
- **Pipeline** — Python 3.14, httpx (async), BeautifulSoup + lxml, Playwright, feedparser
- **Database** — Postgres on Neon: tsvector full-text search, pgvector for retrieval
- **AI** — Claude Sonnet drafts the briefs; Claude Haiku answers Ask the record and runs advisory post-collection validation; OpenAI embeddings for retrieval. AI never writes to the corpus.
- **Auth** — better-auth with Google OAuth, Drizzle adapter
- **Hosting** — Vercel (frontend), Neon (database), GitHub Actions (cron + CI)

## Getting started

```bash
pnpm install
pnpm dev
```

Open [http://localhost:3003](http://localhost:3003). Set `DATABASE_URL` in `.env.local`. `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` enable Ask the record; without them the section stays hidden and everything else works.

## Pipeline CLI

```bash
python -m pipeline update          # collect new releases (cron runs this 4x daily)
python -m pipeline health          # per-member pre-scrape canary
python -m pipeline test            # data-quality suite against the live corpus
python -m pipeline back-coverage   # flag members with truncated archives
python -m pipeline deletions       # detect source-deleted releases
python -m pipeline brief           # generate the daily brief (--weekly for recap)
python -m pipeline floor-speeches  # collect the Congressional Record
python -m pipeline daily-report    # operator digest email
python -m pipeline stats           # database overview
```

Additional commands: `repair`, `review`, `verify-visual`, `tiers`, `source-profiles`, `sync-members`.

## Workflows

| Workflow | Schedule | Job |
|----------|----------|-----|
| `ci.yml` | push / PR | eslint, tsc, non-DB pytest |
| `daily.yml` | 4x daily | collect, embed, data-quality gate |
| `daily-digest.yml` | nightly | operator digest to `ALERT_EMAIL` |
| `brief.yml` | Tue–Sat | daily brief |
| `brief-weekly.yml` | Fri | weekly recap |
| `weekly.yml` | weekly | deep checks |

## Design principles

1. **Determinism first.** AI assists, never drives. Every database write is traceable to a collector run.
2. **Per-member accountability.** A broken collector must not hide in hundreds of healthy ones.
3. **Provenance everywhere.** Every date carries `date_source` and `date_confidence`. Every record carries `source_url`, `scrape_run`, and `scraped_at`.
4. **Collect wide, surface narrow.** Store everything original. Show press releases by default; classify the rest.
5. **No silent failures.** Zero records for a member is an alert unless explicitly expected. Steps that may fail softly have tripwire tests that surface in the daily digest.
6. **Archival permanence.** Never hard-delete. Source-deleted releases become tombstones with `deleted_at` set.
7. **Config over code.** Adding a member, chamber, or jurisdiction is a seed-file change, not a rewrite.

## Scope

- **Current holders only.** Where a seat changed hands during the window, only the current holder's releases are collected.
- **Original content only.** Curated third-party clippings and "In the News" mentions are skipped.
- **Official channels only.** Official .gov sites, verified social accounts, and the Congressional Record — no campaign content.

## Status

U.S. Senate and House run at production quality with daily collection and a 30-plus-test data-quality gate; documented gaps remain on a small number of CMS-truncated archives. The state tier is beta. See `docs/devlog.md` (gitignored) for session-level history.

## Roadmap

- Re-launch subscriber email with double opt-in and per-IP rate limiting on subscribe. The first iteration shipped without either and was retired 2026-08-03 before any subscriber signed up; the weekly recap continues to publish on-site. The send path is preserved in `pipeline/commands/brief_send.py`.

## License

All rights reserved. Source code is public for transparency; reuse requires permission.
