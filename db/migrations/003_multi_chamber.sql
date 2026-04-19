-- Capitol Releases: multi-chamber support
-- Adds chamber column so the senators table can hold non-Senate entities
-- (White House, future House members). Existing rows backfill to 'senate'.
-- Safe to run multiple times.

ALTER TABLE senators ADD COLUMN IF NOT EXISTS chamber TEXT NOT NULL DEFAULT 'senate';

-- Explicit backfill for any rows that predate the default.
UPDATE senators SET chamber = 'senate' WHERE chamber IS NULL OR chamber = '';

CREATE INDEX IF NOT EXISTS idx_senators_chamber ON senators(chamber);
