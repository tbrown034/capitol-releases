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
  rss_feed_url    TEXT,                    -- RSS feed URL if available
  collection_method TEXT,                  -- rss, httpx, playwright, whitehouse
  chamber         TEXT NOT NULL DEFAULT 'senate', -- senate, house, executive
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Press releases (all original senator communications)
CREATE TABLE IF NOT EXISTS press_releases (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  senator_id      TEXT NOT NULL REFERENCES senators(id),
  title           TEXT NOT NULL,
  published_at    TIMESTAMPTZ,
  body_text       TEXT,
  source_url      TEXT NOT NULL UNIQUE,     -- natural dedup key
  raw_html        TEXT,                     -- for re-parsing later
  content_type    TEXT DEFAULT 'press_release', -- press_release, statement, op_ed, letter, photo_release, floor_statement, other
  date_source     TEXT,                    -- feed, meta_tag, json_ld, url_path, page_text, unknown
  date_confidence REAL,                    -- 0.0-1.0 extraction confidence
  content_hash    TEXT,                    -- SHA-256 of body_text for change detection
  deleted_at      TIMESTAMPTZ,            -- tombstone: when we detected deletion at source
  last_seen_live  TIMESTAMPTZ,            -- last time source URL returned 200
  scrape_run      TEXT,                    -- identifies which crawl produced this
  scraped_at      TIMESTAMPTZ DEFAULT NOW(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Query indexes
CREATE INDEX IF NOT EXISTS idx_pr_senator    ON press_releases(senator_id);
CREATE INDEX IF NOT EXISTS idx_pr_published  ON press_releases(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_pr_source     ON press_releases(source_url);
CREATE INDEX IF NOT EXISTS idx_pr_content_type ON press_releases(content_type);
CREATE INDEX IF NOT EXISTS idx_pr_senator_published ON press_releases(senator_id, published_at DESC);

-- Full-text search
ALTER TABLE press_releases ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body_text,''))
  ) STORED;
CREATE INDEX IF NOT EXISTS idx_pr_fts ON press_releases USING GIN(fts);

-- Scrape runs for pipeline health tracking
CREATE TABLE IF NOT EXISTS scrape_runs (
  id          TEXT PRIMARY KEY,            -- 'daily-2026-04-17-0600'
  run_type    TEXT NOT NULL,               -- 'backfill' or 'daily'
  started_at  TIMESTAMPTZ DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  stats       JSONB                        -- records inserted, errors, skipped, etc.
);

-- Health checks (pre-scrape canary results)
CREATE TABLE IF NOT EXISTS health_checks (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  senator_id    TEXT NOT NULL REFERENCES senators(id),
  checked_at    TIMESTAMPTZ DEFAULT NOW(),
  url_status    INTEGER,              -- HTTP status code
  selector_ok   BOOLEAN,
  items_found   INTEGER,
  date_parseable BOOLEAN,
  page_load_ms  INTEGER,
  error_message TEXT,
  passed        BOOLEAN NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hc_senator ON health_checks(senator_id, checked_at DESC);

-- Alerts for pipeline monitoring
CREATE TABLE IF NOT EXISTS alerts (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  alert_type    TEXT NOT NULL,         -- scrape_failure, selector_broken, cms_changed, deletion_detected
  senator_id    TEXT REFERENCES senators(id),
  severity      TEXT NOT NULL,         -- info, warning, error, critical
  message       TEXT NOT NULL,
  details       JSONB,
  acknowledged  BOOLEAN DEFAULT FALSE,
  acknowledged_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type, created_at DESC);

-- Content versions (track body text changes over time)
CREATE TABLE IF NOT EXISTS content_versions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  press_release_id  UUID NOT NULL REFERENCES press_releases(id),
  body_text         TEXT,
  content_hash      TEXT,
  captured_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cv_release ON content_versions(press_release_id, captured_at DESC);

-- Daily AI brief (derivative product; canonical record stays in press_releases)
CREATE TABLE IF NOT EXISTS briefs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brief_date          DATE NOT NULL,
  edition             TEXT NOT NULL DEFAULT 'daily',
  status              TEXT NOT NULL DEFAULT 'draft',
  model_version       TEXT NOT NULL,
  prompt_hash         TEXT NOT NULL,
  headline            TEXT NOT NULL,
  dek                 TEXT,
  lede                TEXT NOT NULL,
  sections            JSONB NOT NULL,
  signals             JSONB,
  silent              JSONB,
  external_context    JSONB,
  source_release_ids  UUID[] NOT NULL,
  cited_release_ids   UUID[] NOT NULL,
  input_tokens        INTEGER,
  output_tokens       INTEGER,
  cost_usd            NUMERIC(10,6),
  generated_at        TIMESTAMPTZ DEFAULT NOW(),
  published_at        TIMESTAMPTZ,
  retracted_at        TIMESTAMPTZ,
  retracted_reason    TEXT,
  quotes              JSONB
);
CREATE INDEX IF NOT EXISTS idx_briefs_date_edition ON briefs(brief_date DESC, edition);
CREATE INDEX IF NOT EXISTS idx_briefs_status_date ON briefs(status, brief_date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_briefs_published_unique
  ON briefs(brief_date, edition)
  WHERE status = 'published';

-- Newsletter subscribers (daily brief email distribution)
CREATE TABLE IF NOT EXISTS newsletter_subscribers (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email               TEXT NOT NULL UNIQUE,
  status              TEXT NOT NULL DEFAULT 'active',
  unsubscribe_token   UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
  subscribed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  unsubscribed_at     TIMESTAMPTZ,
  last_sent_brief_id  UUID REFERENCES briefs(id),
  last_sent_at        TIMESTAMPTZ,
  source              TEXT,
  CONSTRAINT subscribers_status_check CHECK (status IN ('active', 'unsubscribed', 'bounced'))
);
CREATE INDEX IF NOT EXISTS idx_subscribers_status ON newsletter_subscribers(status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_subscribers_token ON newsletter_subscribers(unsubscribe_token);
