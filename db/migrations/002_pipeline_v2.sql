-- Capitol Releases: Pipeline v2 schema additions
-- All additive -- no drops, no destructive changes.
-- Safe to run multiple times (IF NOT EXISTS / IF NOT EXISTS throughout).

-- Senators: collection method and RSS feed tracking
ALTER TABLE senators ADD COLUMN IF NOT EXISTS rss_feed_url TEXT;
ALTER TABLE senators ADD COLUMN IF NOT EXISTS collection_method TEXT;

-- Press releases: content classification
ALTER TABLE press_releases ADD COLUMN IF NOT EXISTS content_type TEXT DEFAULT 'press_release';

-- Press releases: date provenance
ALTER TABLE press_releases ADD COLUMN IF NOT EXISTS date_source TEXT;
ALTER TABLE press_releases ADD COLUMN IF NOT EXISTS date_confidence REAL;

-- Press releases: content identity and versioning
ALTER TABLE press_releases ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE press_releases ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Better indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_pr_content_type ON press_releases(content_type);
CREATE INDEX IF NOT EXISTS idx_pr_senator_published ON press_releases(senator_id, published_at DESC);
