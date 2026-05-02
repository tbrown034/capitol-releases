-- Capitol Releases: add district column to members
--
-- House members and state-house members carry a district number (or
-- 'At-Large' for single-district states / non-voting delegates).
-- Senate members and executives leave it null.
--
-- Idempotent.

ALTER TABLE senators ADD COLUMN IF NOT EXISTS district TEXT;

-- Composite index supporting per-state, per-chamber roster lookups
-- ("all CA House members", "all NY senators"). status filter intentionally
-- omitted -- a query for "all of NY's delegation including former members"
-- is a legitimate journalist use case.
CREATE INDEX IF NOT EXISTS idx_senators_state_chamber_district
  ON senators(state, chamber, district);
