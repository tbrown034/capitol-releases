-- Capitol Releases: social_posts
--
-- Senator-authored social posts, kept separate from press_releases for now.
-- The /social surface reads from this table; the main feed (/) does not.
-- A future unified-feed view can UNION across both tables, but the
-- distinction stays at the storage layer so each source keeps its own
-- provenance discipline.
--
-- Initial source = 'bluesky'. The `source` discriminator + composite
-- natural key on (source, platform_post_id) lets us add other platforms
-- later without breaking the upsert path.
--
-- Idempotent.

CREATE TABLE IF NOT EXISTS social_posts (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  senator_id        TEXT NOT NULL REFERENCES senators(id),
  source            TEXT NOT NULL,                -- 'bluesky'
  platform_post_id  TEXT NOT NULL,                -- AT URI for bluesky (at://did/app.bsky.feed.post/<rkey>)
  cid               TEXT,                         -- AT Protocol content hash
  did               TEXT NOT NULL,                -- author DID (stable; handle can change)
  handle            TEXT NOT NULL,                -- author handle at time of capture
  text              TEXT NOT NULL,                -- post body
  created_at        TIMESTAMPTZ NOT NULL,         -- author-reported post time
  is_reply          BOOLEAN NOT NULL DEFAULT FALSE,
  reply_parent_uri  TEXT,                         -- AT URI of parent if reply
  is_repost         BOOLEAN NOT NULL DEFAULT FALSE,
  embed_kind        TEXT,                         -- 'external' | 'record' | 'images' | 'video' | NULL
  embed_summary     TEXT,                         -- short human-readable hint (e.g. 'link:https://...')
  lang              TEXT,                         -- BCP-47 if reported
  raw               JSONB NOT NULL,               -- complete post object for re-parse
  scraped_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  scrape_run        TEXT,                         -- which crawl produced this row
  deleted_at        TIMESTAMPTZ,                  -- tombstone if Jetstream sees a delete
  CONSTRAINT social_posts_source_check
    CHECK (source IN ('bluesky')),
  CONSTRAINT social_posts_natural_uniq
    UNIQUE (source, platform_post_id)
);

CREATE INDEX IF NOT EXISTS idx_social_senator_created
  ON social_posts (senator_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_created
  ON social_posts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_did
  ON social_posts (did);
CREATE INDEX IF NOT EXISTS idx_social_live
  ON social_posts (created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_social_reply
  ON social_posts (senator_id, created_at DESC) WHERE is_reply = FALSE AND deleted_at IS NULL;
