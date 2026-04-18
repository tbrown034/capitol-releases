@AGENTS.md

# Capitol Releases

A journalism/public-records app for Congress, starting with the U.S. Senate. Collects, archives, and monitors all official communications from 100 senators.

## What This Is

A normalized, searchable, archival-grade corpus of Senate press releases and official communications. The product value is reliability, provenance, and accountability features (deletion detection, content versioning) that no existing tool provides.

## Architecture

Python scraping pipeline with collector pattern, feeding a Next.js frontend via Postgres.

| Component | Purpose |
|-----------|---------|
| **Recon** (completed) | Discovered all 100 Senate press-release sections, classified CMS types, generated seed config |
| **Collectors** | RSS (24 senators), httpx + selectors (68), Playwright (8 pending). Each senator gets a canonical collector. |
| **Daily Updater** | Runs every 2-4 hours weekdays. Fetches page 1, dedup on source_url, ~2 min runtime. |
| **Health Checks** | Pre-scrape canary verifying URLs, selectors, feeds per senator. |
| **Anomaly Detection** | Post-run checks for stale senators, null-date spikes, collection gaps. |
| **Deletion Detection** | Periodic GET verification of source URLs. Tombstones, never hard-deletes. |
| **AI Validation** | Claude Haiku post-collection quality check. Advisory only, never silent writes. |

## Stack

- **Pipeline**: Python (httpx, BeautifulSoup, Playwright, feedparser)
- **Frontend**: Next.js (App Router), React 19, Tailwind, TypeScript
- **Database**: Postgres (Neon) with full-text search (tsvector), provenance columns
- **AI**: Anthropic Claude API (Haiku for validation, advisory)
- **Alerts**: Resend SMTP for email notifications
- **Deployment**: Vercel (frontend), pipeline local/cron (deployment TBD)

## Pipeline CLI

```bash
python -m pipeline update          # collect new releases
python -m pipeline health          # run health checks
python -m pipeline test            # data quality tests
python -m pipeline stats           # database overview
python -m pipeline review quality  # data quality details
python -m pipeline deletions       # check for deleted releases
```

## Content Scope

Collects all original senator communications (press releases, statements, op-eds, letters, photo releases, floor statements). Product default surfaces press releases. Other types classified and internally modeled.

## Data Window

Historical: January 1, 2025 to present. Daily updates ongoing.

## Key Principles

1. Determinism first. AI assists but doesn't drive.
2. Per-senator, not aggregate. One broken senator must not hide in 99 healthy ones.
3. Provenance everywhere. Every date carries source and confidence.
4. Collect wide, surface narrow.
5. No silent failures.
6. Archival permanence. Never hard-delete.

*Last updated: April 17, 2026*
