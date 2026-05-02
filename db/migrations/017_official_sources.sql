-- Capitol Releases: official_sources schema split (steps 1-2 of the
-- 2026-05-02 migration plan, with a primary-source backfill).
--
-- Rationale (see docs/official-sources-migration-plan-2026-05-02.md):
--   Today's `officials` table bakes a single collection path per member
--   into the same row that holds identity (press_release_url,
--   rss_feed_url, collection_method, parser_family, scrape_config,
--   requires_js, confidence, last_verified). House wave-2 proved that
--   most members publish to several channels per office (press releases,
--   op-eds, newsletters, speeches), each potentially needing its own
--   selectors and pagination. State-house expansion (~7,400 members ×
--   3-7 channels each) compounds that.
--
--   This migration introduces `official_sources` -- one row per
--   (official, channel). The legacy collection columns on `officials`
--   are NOT dropped here; both shapes coexist during the cutover.
--   Step 9 of the plan drops them after a 1-week soak.
--
-- Idempotent. Safe to re-run. Each statement guards against having run
-- before, either via IF [NOT] EXISTS or ON CONFLICT DO NOTHING.

-- ---------------------------------------------------------------------
-- Step 1 -- create official_sources + indexes.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS official_sources (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  official_id       TEXT NOT NULL REFERENCES officials(id),
  -- 'rss' | 'html_listing' | 'wp_json' | 'bluesky' | 'govinfo_crec' | 'caucus_site'
  source_type       TEXT NOT NULL,
  -- 'press_release' | 'statement' | 'op_ed' | 'blog' | 'newsletter' |
  -- 'floor_statement' | 'letter' | 'photo_release' | 'other'
  content_scope     TEXT NOT NULL,
  url               TEXT NOT NULL,
  -- 'rss' | 'httpx' | 'playwright' | 'whitehouse' | 'tx_senate' |
  -- 'ne_unicameral' | 'ca_senate' | 'oh_senate' | 'mo_senate_newsroom' |
  -- 'wv_legislature_news'
  collection_method TEXT NOT NULL,
  -- selectors + pagination + notes for HTML listings
  scrape_config     JSONB,
  parser_family     TEXT,
  active            BOOLEAN NOT NULL DEFAULT TRUE,
  last_verified     TIMESTAMPTZ,
  last_seen_live    TIMESTAMPTZ,
  confidence        REAL,
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_official_source_url UNIQUE (official_id, url)
);

CREATE INDEX IF NOT EXISTS idx_official_sources_official_id
  ON official_sources(official_id);
CREATE INDEX IF NOT EXISTS idx_official_sources_active
  ON official_sources(active) WHERE active = TRUE;
CREATE INDEX IF NOT EXISTS idx_official_sources_content_scope
  ON official_sources(content_scope);
CREATE INDEX IF NOT EXISTS idx_official_sources_source_type
  ON official_sources(source_type);

-- ---------------------------------------------------------------------
-- Step 2 -- backfill primary sources from existing `officials` rows.
--
-- Every official with a non-null collection_method gets at least one
-- official_sources row (their default press_release source). House
-- members that have BOTH a real rss_feed_url AND a separate
-- press_release_url get TWO rows -- one for daily RSS collection and
-- one for the HTML listing used by backfill.
--
-- The "shape" of each row:
--   * Primary HTML/listing row: source_type derived from the
--     collection_method ('rss' -> 'rss', everything else -> 'html_listing'),
--     content_scope='press_release', url=COALESCE(rss_feed_url for rss
--     methods, press_release_url otherwise).
--   * Secondary RSS row (House dual-channel only): source_type='rss',
--     collection_method='rss', url=rss_feed_url, content_scope='press_release'.
--
-- ON CONFLICT DO NOTHING on uq_official_source_url makes this re-runnable.
-- ---------------------------------------------------------------------

-- 2a. Primary source: one row per official with a non-null collection_method.
--     For officials whose collection_method='rss', the primary URL is the
--     rss_feed_url (source_type='rss'). For everyone else it's
--     press_release_url (source_type='html_listing').
INSERT INTO official_sources (
  official_id, source_type, content_scope, url, collection_method,
  scrape_config, parser_family, confidence, last_verified, active, notes
)
SELECT
  o.id AS official_id,
  CASE
    WHEN o.collection_method = 'rss' THEN 'rss'
    ELSE 'html_listing'
  END AS source_type,
  'press_release' AS content_scope,
  CASE
    WHEN o.collection_method = 'rss' THEN COALESCE(o.rss_feed_url, o.press_release_url)
    ELSE COALESCE(o.press_release_url, o.rss_feed_url)
  END AS url,
  o.collection_method,
  o.scrape_config,
  o.parser_family,
  o.confidence,
  o.last_verified,
  TRUE AS active,
  'backfilled from officials row by migration 017' AS notes
FROM officials o
WHERE o.collection_method IS NOT NULL
  -- Skip rows where we'd end up with a NULL url -- those are
  -- collection methods (whitehouse, tx_senate, ne_unicameral, etc.)
  -- that don't carry a per-official URL on the officials row. Their
  -- collectors derive URLs internally; backfill them via a follow-up
  -- if/when a per-official source row is needed.
  AND COALESCE(
    CASE WHEN o.collection_method = 'rss' THEN o.rss_feed_url ELSE o.press_release_url END,
    CASE WHEN o.collection_method = 'rss' THEN o.press_release_url ELSE o.rss_feed_url END
  ) IS NOT NULL
ON CONFLICT ON CONSTRAINT uq_official_source_url DO NOTHING;

-- 2b. Secondary RSS source for House members that have BOTH an
--     rss_feed_url AND a separate press_release_url. The 89 RSS-active
--     House members from wave-2 fit this pattern: daily collection from
--     RSS for speed/freshness, HTML listing for deep backfill. The 2a
--     INSERT above already inserted one of these (the one matching their
--     collection_method); 2b adds the other.
INSERT INTO official_sources (
  official_id, source_type, content_scope, url, collection_method,
  scrape_config, parser_family, confidence, last_verified, active, notes
)
SELECT
  o.id AS official_id,
  'rss' AS source_type,
  'press_release' AS content_scope,
  o.rss_feed_url AS url,
  'rss' AS collection_method,
  NULL::jsonb AS scrape_config,  -- RSS sources don't carry HTML selectors
  o.parser_family,
  o.confidence,
  o.last_verified,
  TRUE AS active,
  'secondary RSS feed; backfilled by migration 017' AS notes
FROM officials o
WHERE o.collection_method IS NOT NULL
  AND o.collection_method <> 'rss'
  AND o.rss_feed_url IS NOT NULL
  AND o.press_release_url IS NOT NULL
  AND o.rss_feed_url <> o.press_release_url
ON CONFLICT ON CONSTRAINT uq_official_source_url DO NOTHING;

-- 2c. Symmetric case: officials whose primary collection_method='rss'
--     but who also expose a different press_release_url for HTML
--     backfill. Add the HTML listing as a secondary source so backfill
--     can find it without falling back to the legacy column.
INSERT INTO official_sources (
  official_id, source_type, content_scope, url, collection_method,
  scrape_config, parser_family, confidence, last_verified, active, notes
)
SELECT
  o.id AS official_id,
  'html_listing' AS source_type,
  'press_release' AS content_scope,
  o.press_release_url AS url,
  'httpx' AS collection_method,
  o.scrape_config,
  o.parser_family,
  o.confidence,
  o.last_verified,
  TRUE AS active,
  'secondary HTML listing; backfilled by migration 017' AS notes
FROM officials o
WHERE o.collection_method = 'rss'
  AND o.press_release_url IS NOT NULL
  AND o.rss_feed_url IS NOT NULL
  AND o.press_release_url <> o.rss_feed_url
ON CONFLICT ON CONSTRAINT uq_official_source_url DO NOTHING;

-- ---------------------------------------------------------------------
-- Step 3 (silos) is handled by pipeline/scripts/migrate_silos_to_sources.py
-- rather than inline SQL, since it reads pipeline/recon/house_full_recon.json
-- (file-system input that doesn't belong in a SQL migration).
-- ---------------------------------------------------------------------
