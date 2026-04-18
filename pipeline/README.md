# Capitol Releases Pipeline

Python scraping pipeline for collecting, archiving, and monitoring U.S. Senate press releases.

## Quick Start

```bash
# Setup
cd pipeline
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your DATABASE_URL and ANTHROPIC_API_KEY

# Run
python -m pipeline update              # collect new releases
python -m pipeline update --dry-run    # preview without inserting
python -m pipeline health --method rss # check RSS feed health
python -m pipeline test                # run data quality tests
python -m pipeline stats              # database overview
python -m pipeline review quality      # data quality details
python -m pipeline review alerts       # unacknowledged alerts
python -m pipeline review stale        # senators with old data
python -m pipeline review runs         # recent scrape runs
python -m pipeline deletions           # check for deleted releases
```

## Architecture

```
pipeline/
  lib/              # Shared utilities
    dates.py        # Unified date parsing with provenance
    http.py         # HTTP client with retry
    classifier.py   # Content type classification
    identity.py     # URL normalization + content hashing
    rss.py          # RSS feed discovery and parsing
    alerts.py       # Anomaly detection + email alerts
    ai_validator.py # Claude Haiku validation (advisory)

  collectors/       # Collection strategies
    base.py         # Collector protocol
    rss_collector.py    # RSS feeds (24 senators)
    httpx_collector.py  # Static HTML (68 senators)
    registry.py         # Routes senators to collectors

  commands/         # CLI entry points
    update.py           # Daily updater (Script 3)
    health_check.py     # Pre-scrape canary
    detect_deletions.py # Tombstone detection
    review.py           # Operator review surface

  seeds/            # Configuration
    senate.json     # Per-senator config (URLs, selectors, methods)

  tests/            # Data quality tests (16 tests)
  recon/            # Site discovery (completed)
```

## Collection Methods

Each senator is assigned a canonical collector:

| Method | Senators | How it works |
|--------|----------|-------------|
| RSS | 24 | Parse RSS/Atom feeds. Most reliable -- no selectors to break. |
| httpx | 68 | Fetch HTML + CSS selectors. Battle-tested across 8+ CMS types. |
| Playwright | 8 | Headless browser for JS-rendered sites. Pending full integration. |

## Database

Postgres (Neon) with:
- `senators` -- 100 senator configs
- `press_releases` -- all collected releases with provenance
- `health_checks` -- per-senator health monitoring
- `alerts` -- anomaly and failure alerts
- `scrape_runs` -- pipeline run history
- `content_versions` -- body text change tracking
- Full-text search via tsvector + GIN index

## Key Principles

1. **Determinism first.** Deterministic collectors are the canonical path. AI assists but doesn't drive.
2. **Per-senator, not aggregate.** One broken senator must not hide in 99 healthy ones.
3. **Provenance everywhere.** Every date carries source and confidence.
4. **Collect wide, surface narrow.** Ingest all original communications. Default to press releases.
5. **No silent failures.** Every error is logged, every anomaly is alerted.
6. **Archival permanence.** Never hard-delete. Deletions become tombstones.
