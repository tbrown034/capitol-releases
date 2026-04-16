-- Capitol Releases database schema
-- Neon Postgres (via Vercel)

-- Senators reference table
CREATE TABLE IF NOT EXISTS senators (
  id              TEXT PRIMARY KEY,        -- 'warren-elizabeth'
  full_name       TEXT NOT NULL,
  party           TEXT NOT NULL,           -- 'D', 'R', 'I'
  state           CHAR(2) NOT NULL,
  official_url    TEXT NOT NULL,
  press_release_url TEXT,
  parser_family   TEXT,
  scrape_config   JSONB,                   -- selectors, pagination, notes
  requires_js     BOOLEAN DEFAULT FALSE,
  confidence      REAL,
  last_verified   TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Press releases
CREATE TABLE IF NOT EXISTS press_releases (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  senator_id      TEXT NOT NULL REFERENCES senators(id),
  title           TEXT NOT NULL,
  published_at    TIMESTAMPTZ,
  body_text       TEXT,
  source_url      TEXT NOT NULL UNIQUE,     -- natural dedup key
  raw_html        TEXT,                     -- for re-parsing later
  scrape_run      TEXT,                     -- identifies which crawl produced this
  scraped_at      TIMESTAMPTZ DEFAULT NOW(),
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Query indexes
CREATE INDEX IF NOT EXISTS idx_pr_senator    ON press_releases(senator_id);
CREATE INDEX IF NOT EXISTS idx_pr_published  ON press_releases(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_pr_source     ON press_releases(source_url);

-- Full-text search
ALTER TABLE press_releases ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body_text,''))
  ) STORED;
CREATE INDEX IF NOT EXISTS idx_pr_fts ON press_releases USING GIN(fts);

-- Scrape runs for pipeline health tracking
CREATE TABLE IF NOT EXISTS scrape_runs (
  id          TEXT PRIMARY KEY,            -- 'backfill-2026-04-15' or 'daily-2026-04-15'
  run_type    TEXT NOT NULL,               -- 'backfill' or 'daily'
  started_at  TIMESTAMPTZ DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  stats       JSONB                        -- records inserted, errors, skipped, etc.
);
