@AGENTS.md

# Capitol Releases

A journalism/public-records app for Congress, starting with the U.S. Senate. First product focus: official press releases from all 100 senators.

## What This Is

A normalized, searchable, analyzable archive of Senate press releases. No clean API exists for this data, so the product value is in discovering each senator's press-release section, understanding the structure, normalizing the output and maintaining a clean feed.

## Architecture

Three-stage Python scraping pipeline feeding a Next.js frontend via Postgres.

| Stage | Purpose |
|-------|---------|
| **Script 1: Recon** | Visit all 100 Senate sites, discover press-release sections, classify parser patterns, generate seed config |
| **Script 2: Backfill** | Crawl historical press releases from Jan 1 2025 to present using the seed config |
| **Script 3: Updater** | Daily job to check for new releases since last run, insert new records only |

## Stack

- **Scraping pipeline**: Python (Scrapy + scrapy-playwright for JS-rendered sites)
- **Frontend**: Next.js (App Router), React 19, Tailwind, TypeScript
- **Database**: Postgres with full-text search (tsvector), JSONB for scrape metadata
- **Deployment**: Vercel (frontend), pipeline TBD

## Data Window

Historical collection starts January 1, 2025. Ongoing daily updates after backfill.

## Product Surface

- Reverse-chronological feed with filters (senator, party, state, date)
- Keyword/topic search
- Light analytics: posting frequency, sparklines, baseline-vs-spike detection
- Future: topic tagging, semantic search, clustering, LLM analysis

*Last updated: April 15, 2026*
