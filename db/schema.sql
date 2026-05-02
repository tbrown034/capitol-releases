-- Capitol Releases database schema
-- Neon Postgres (via Vercel)
--
-- Renamed from `senators` -> `officials` and `press_releases` ->
-- `official_site_items` on 2026-05-02 (migrations 012, 013, 014, 015) so
-- the schema fits the realized goal — every elected official at federal
-- and state level, multiple content streams each. Compat views named
-- `senators` and `press_releases` exist temporarily for unswept callers
-- and are dropped in a follow-up migration once the codebase is clean.

-- Officials reference table — every person we cover, legislator or executive
CREATE TABLE IF NOT EXISTS officials (
  id              TEXT PRIMARY KEY,        -- 'warren-elizabeth' / 'tx-d27-hinojosa-adam' / 'whitehouse'
  full_name       TEXT NOT NULL,
  party           TEXT NOT NULL,           -- 'D', 'R', 'I'
  state           CHAR(2) NOT NULL,        -- state they represent (or operate in for execs)
  official_url    TEXT NOT NULL,
  press_release_url TEXT,
  parser_family   TEXT,
  scrape_config   JSONB,                   -- selectors, pagination, notes
  requires_js     BOOLEAN DEFAULT FALSE,
  confidence      REAL,
  last_verified   TIMESTAMPTZ,
  rss_feed_url    TEXT,                    -- RSS feed URL if available
  collection_method TEXT,                  -- rss, httpx, playwright, whitehouse, tx_senate, ne_unicameral
  -- Structural columns (added 2026-05-02 migration 012). Together they
  -- describe what kind of official this is:
  branch          TEXT NOT NULL,           -- 'legislative' | 'executive'
  jurisdiction    TEXT NOT NULL,           -- 'us' | 'tx' | 'ca' | ... (state codes for state members)
  office_type     TEXT NOT NULL,           -- 'senator' | 'representative' | 'state_senator' | 'executive_office' | (later) 'governor' | ...
  chamber         TEXT,                    -- 'senate' | 'house' | 'unicameral' | NULL (executives)
  district        TEXT,                    -- House district number / 'At-Large'; NULL for senators + executives
  bioguide_id     TEXT,                    -- bioguide.congress.gov ID (federal members only)
  openstates_id   TEXT,                    -- Open States ID (state legislators)
  external_ids    JSONB,                   -- catch-all for future ID systems (FEC, state-specific, etc.)
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_officials_bioguide_id
  ON officials(bioguide_id) WHERE bioguide_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_officials_state_chamber_district
  ON officials(state, chamber, district);
CREATE INDEX IF NOT EXISTS idx_officials_jurisdiction_chamber
  ON officials(jurisdiction, chamber, status);
CREATE INDEX IF NOT EXISTS idx_officials_branch_jurisdiction
  ON officials(branch, jurisdiction);
CREATE INDEX IF NOT EXISTS idx_officials_office_type
  ON officials(office_type);

-- Compat views maintained during the codemod sweep. Drop in a follow-up
-- migration once all callers reference officials / official_site_items
-- directly. The press_releases view exposes both official_id (canonical)
-- and senator_id (legacy alias) so unswept SELECTs keep returning data.
CREATE OR REPLACE VIEW senators AS SELECT * FROM officials;

-- Original content scraped from official .gov sites: press releases,
-- statements, op-eds, blogs, newsletters, floor statements, letters.
-- Social posts (Bluesky) and floor-speech transcripts (Congressional
-- Record) live in their own tables because they have different shapes.
CREATE TABLE IF NOT EXISTS official_site_items (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  official_id     TEXT NOT NULL REFERENCES officials(id),
  title           TEXT NOT NULL,
  published_at    TIMESTAMPTZ,
  body_text       TEXT,
  source_url      TEXT NOT NULL UNIQUE,     -- natural dedup key
  raw_html        TEXT,                     -- for re-parsing later
  content_type    TEXT DEFAULT 'press_release', -- press_release | statement | op_ed | blog | newsletter | floor_statement | letter | photo_release | other
  date_source     TEXT,                    -- feed | meta_tag | json_ld | url_path | page_text | silo_backfill | unknown
  date_confidence REAL,                    -- 0.0-1.0 extraction confidence
  content_hash    TEXT,                    -- SHA-256 of body_text for change detection
  deleted_at      TIMESTAMPTZ,            -- tombstone: set when we detect deletion at source
  last_seen_live  TIMESTAMPTZ,            -- last time source URL returned 200
  scrape_run      TEXT,                    -- identifies which crawl produced this
  scraped_at      TIMESTAMPTZ DEFAULT NOW(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Query indexes
CREATE INDEX IF NOT EXISTS idx_osi_official    ON official_site_items(official_id);
CREATE INDEX IF NOT EXISTS idx_osi_published   ON official_site_items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_osi_source      ON official_site_items(source_url);
CREATE INDEX IF NOT EXISTS idx_osi_content_type ON official_site_items(content_type);
CREATE INDEX IF NOT EXISTS idx_osi_official_published
  ON official_site_items(official_id, published_at DESC);

-- Full-text search
ALTER TABLE official_site_items ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body_text,''))
  ) STORED;
CREATE INDEX IF NOT EXISTS idx_osi_fts ON official_site_items USING GIN(fts);

-- Compat view: press_releases aliases official_site_items and exposes
-- official_id under both its canonical name and the legacy senator_id
-- name. Drop in a follow-up migration once code is clean.
CREATE OR REPLACE VIEW press_releases AS
  SELECT *, official_id AS senator_id FROM official_site_items;

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
  official_id    TEXT NOT NULL REFERENCES officials(id),
  checked_at    TIMESTAMPTZ DEFAULT NOW(),
  url_status    INTEGER,              -- HTTP status code
  selector_ok   BOOLEAN,
  items_found   INTEGER,
  date_parseable BOOLEAN,
  page_load_ms  INTEGER,
  error_message TEXT,
  passed        BOOLEAN NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hc_senator ON health_checks(official_id, checked_at DESC);

-- Alerts for pipeline monitoring
CREATE TABLE IF NOT EXISTS alerts (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  alert_type    TEXT NOT NULL,         -- scrape_failure, selector_broken, cms_changed, deletion_detected
  official_id    TEXT REFERENCES officials(id),
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
  official_site_item_id  UUID NOT NULL REFERENCES official_site_items(id),
  body_text         TEXT,
  content_hash      TEXT,
  captured_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cv_release ON content_versions(official_site_item_id, captured_at DESC);

-- Daily AI brief (derivative product; canonical record stays in official_site_items)
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

-- Senator social posts (Bluesky for now). Kept separate from official_site_items.
CREATE TABLE IF NOT EXISTS social_posts (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  official_id        TEXT NOT NULL REFERENCES officials(id),
  source            TEXT NOT NULL,
  platform_post_id  TEXT NOT NULL,
  cid               TEXT,
  did               TEXT NOT NULL,
  handle            TEXT NOT NULL,
  text              TEXT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL,
  is_reply          BOOLEAN NOT NULL DEFAULT FALSE,
  reply_parent_uri  TEXT,
  is_repost         BOOLEAN NOT NULL DEFAULT FALSE,
  embed_kind        TEXT,
  embed_summary     TEXT,
  lang              TEXT,
  raw               JSONB NOT NULL,
  scraped_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  scrape_run        TEXT,
  deleted_at        TIMESTAMPTZ,
  CONSTRAINT social_posts_source_check CHECK (source IN ('bluesky')),
  CONSTRAINT social_posts_natural_uniq UNIQUE (source, platform_post_id)
);
CREATE INDEX IF NOT EXISTS idx_social_senator_created ON social_posts (official_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_created ON social_posts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_did ON social_posts (did);
CREATE INDEX IF NOT EXISTS idx_social_live ON social_posts (created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_social_reply ON social_posts (official_id, created_at DESC) WHERE is_reply = FALSE AND deleted_at IS NULL;

-- Senate floor speeches from the Congressional Record (govinfo). Kept
-- separate from official_site_items because granule -> speech is one-to-many
-- (multi-speaker debates) and provenance is govinfo, not senator.gov.
CREATE TABLE IF NOT EXISTS floor_speeches (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  granule_id          TEXT NOT NULL,
  bioguide_id         TEXT NOT NULL,
  official_id          TEXT REFERENCES officials(id),
  turn_index          INTEGER NOT NULL DEFAULT 0,
  speech_date         DATE NOT NULL,
  title               TEXT NOT NULL,
  sub_granule_class   TEXT,
  speaker_marker      TEXT NOT NULL,
  party               CHAR(1),
  state               CHAR(2),
  word_count          INTEGER NOT NULL,
  body_text           TEXT NOT NULL,
  is_solo             BOOLEAN NOT NULL,
  detail_url          TEXT NOT NULL,
  html_url            TEXT NOT NULL,
  congress            INTEGER NOT NULL,
  scrape_run          TEXT,
  scraped_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT floor_speeches_natural_uniq
    UNIQUE (granule_id, bioguide_id, turn_index)
);
CREATE INDEX IF NOT EXISTS idx_floor_senator_date   ON floor_speeches (official_id, speech_date DESC);
CREATE INDEX IF NOT EXISTS idx_floor_bioguide_date  ON floor_speeches (bioguide_id, speech_date DESC);
CREATE INDEX IF NOT EXISTS idx_floor_date           ON floor_speeches (speech_date DESC);
CREATE INDEX IF NOT EXISTS idx_floor_granule        ON floor_speeches (granule_id);
CREATE INDEX IF NOT EXISTS idx_floor_subclass       ON floor_speeches (sub_granule_class);

ALTER TABLE floor_speeches ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body_text,''))
  ) STORED;
CREATE INDEX IF NOT EXISTS idx_floor_fts ON floor_speeches USING GIN(fts);
