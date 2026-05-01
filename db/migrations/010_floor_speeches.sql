-- Capitol Releases: floor_speeches
--
-- Senate floor speeches collected from the daily Congressional Record
-- (govinfo.gov), with full speaker attribution via bioguide_id. Kept
-- separate from press_releases because:
--   * granule -> speech is one-to-many (multi-speaker debates)
--   * provenance is govinfo, not the senator's website
--   * senators may also repost the same speech on their /news; we collect
--     both, treating the senator.gov post as a separate copy
--
-- Natural dedup key is (granule_id, bioguide_id, turn_index). A single
-- granule can have multiple speakers; a single speaker can have multiple
-- turns within a debate. Consecutive turns by the same speaker are merged
-- at collection time; this table stores the post-merge rows.
--
-- Idempotent.

ALTER TABLE senators ADD COLUMN IF NOT EXISTS bioguide_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_senators_bioguide_id
  ON senators(bioguide_id) WHERE bioguide_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS floor_speeches (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  granule_id          TEXT NOT NULL,                  -- CREC-2026-04-29-pt1-PgS2091
  bioguide_id         TEXT NOT NULL,                  -- K000393
  senator_id          TEXT REFERENCES senators(id),   -- nullable until senators row exists
  turn_index          INTEGER NOT NULL DEFAULT 0,     -- 0 for solo granule; 0..N for multi-speaker
  speech_date         DATE NOT NULL,                  -- granule date (CR publication date)
  title               TEXT NOT NULL,
  sub_granule_class   TEXT,                           -- ALLOTHER, RECOGNIZING, TRIBUTETO, ...
  speaker_marker      TEXT NOT NULL,                  -- "Mr. KENNEDY"
  party               CHAR(1),
  state               CHAR(2),
  word_count          INTEGER NOT NULL,
  body_text           TEXT NOT NULL,
  is_solo             BOOLEAN NOT NULL,
  detail_url          TEXT NOT NULL,                  -- govinfo detail page
  html_url            TEXT NOT NULL,                  -- raw HTM rendition
  congress            INTEGER NOT NULL,
  scrape_run          TEXT,
  scraped_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT floor_speeches_natural_uniq
    UNIQUE (granule_id, bioguide_id, turn_index)
);

CREATE INDEX IF NOT EXISTS idx_floor_senator_date
  ON floor_speeches (senator_id, speech_date DESC);
CREATE INDEX IF NOT EXISTS idx_floor_bioguide_date
  ON floor_speeches (bioguide_id, speech_date DESC);
CREATE INDEX IF NOT EXISTS idx_floor_date
  ON floor_speeches (speech_date DESC);
CREATE INDEX IF NOT EXISTS idx_floor_granule
  ON floor_speeches (granule_id);
CREATE INDEX IF NOT EXISTS idx_floor_subclass
  ON floor_speeches (sub_granule_class);

-- Full-text search across speech bodies
ALTER TABLE floor_speeches ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body_text,''))
  ) STORED;
CREATE INDEX IF NOT EXISTS idx_floor_fts ON floor_speeches USING GIN(fts);
