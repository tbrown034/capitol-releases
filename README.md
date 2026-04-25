# Capitol Releases

A journalism and public-records project that builds an archival-grade, searchable corpus of every original press release, statement, op-ed, and blog post from each of the 100 current U.S. senators.

Live at **[capitolreleases.com](https://capitolreleases.com)**.

## What it does

Capitol Releases collects communications from every senator's official `senate.gov` site daily, normalizes them into a single schema, and exposes them through a Next.js frontend with full-text search, a per-senator dashboard, and release-volume analytics.

Coverage starts January 1, 2025. Every record carries provenance — source URL, scrape run, date confidence — and deletions at the source are preserved as tombstones rather than removed.

## Repository layout

| Path | Purpose |
|------|---------|
| `app/` | Next.js 16 frontend (App Router, React 19, Tailwind 4) |
| `pipeline/` | Python collection pipeline, CLI, tests, backfill scripts |
| `pipeline/seeds/senate.json` | Per-senator URL, CMS family, selectors, collection method |
| `pipeline/collectors/` | RSS, httpx, and Playwright-driven collectors |
| `pipeline/commands/` | CLI subcommands — update, health, test, deletions, repair |
| `db/` | Postgres schema and migrations |
| `.github/workflows/` | Daily and weekly cron jobs |

## Stack

- **Frontend** — Next.js 16, React 19, Tailwind 4, TypeScript, D3
- **Pipeline** — Python 3.14, httpx, BeautifulSoup, lxml, Playwright, feedparser
- **Database** — Postgres on Neon (full-text search via tsvector)
- **AI** — Claude Haiku 4.5 for post-collection quality checks
- **Hosting** — Vercel (frontend), Neon (database), GitHub Actions (cron)

## Frontend — getting started

```bash
pnpm install
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000). Set `DATABASE_URL` in `.env.local` to point at a Neon branch.

## Pipeline CLI

```bash
python -m pipeline update          # collect new releases (daily)
python -m pipeline health          # per-senator canary
python -m pipeline test            # data quality suite
python -m pipeline back-coverage   # flag senators with truncated archives
python -m pipeline stats           # database overview
python -m pipeline review quality  # detailed quality breakdown
python -m pipeline deletions       # detect deleted releases
python -m pipeline repair          # targeted fixes for known-broken senators
python -m pipeline verify-visual   # compare DB vs live site for drift
```

Daily and weekly runs are scheduled via GitHub Actions in `.github/workflows/`.

## Design principles

1. **Determinism first.** AI assists, never drives. Every database write is traceable to a collector run.
2. **Per-senator accountability.** A broken senator must not hide in 99 healthy ones.
3. **Provenance everywhere.** Every date carries `date_source` and `date_confidence`. Every record carries `source_url`, `scrape_run`, and `scraped_at`.
4. **Collect wide, surface narrow.** Store everything original. Show press releases by default; classify the rest.
5. **No silent failures.** Zero records for a senator is a P0 alert unless explicitly whitelisted.
6. **Archival permanence.** Never hard-delete. Source-deleted releases become tombstones with `deleted_at` set.
7. **House-ready.** Schema, config, and UI treat "senator" as one member type — adding House members is a config change, not a rewrite.

## Scope

- **Current holders only.** Where a seat changed hands during the window, only the current holder's releases are collected.
- **Original content only.** Curated third-party clippings and "In the News" mentions are skipped.
- **Senate first.** House expansion is a later phase, but the architecture is chamber-agnostic today.

## Status

Around 30,000 records across 100 senators, with daily updates running. Coverage is near-complete for 2025–present, with documented gaps on a small number of CMS-truncated archives. See `docs/devlog.md` (gitignored) for session-level history.

## License

All rights reserved. Source code is public for transparency; reuse requires permission.
