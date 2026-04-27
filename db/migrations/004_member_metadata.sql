-- Capitol Releases: formalize member metadata columns
--
-- The site has been reading these columns out of senators in production for
-- months (status filter on every UI query, bioguide_id for headshots,
-- senate_class / first_term_start / current_term_end for the directory's
-- "Years in office" + "Next election" cells, left_date / left_reason for the
-- former-senator badge on profile pages). They were added ad-hoc against the
-- live Neon DB and never made it into version control. A new Neon branch (or
-- a fresh local checkout) will fail at runtime without them.
--
-- This migration captures the current production shape. Idempotent.

ALTER TABLE senators ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE senators ADD COLUMN IF NOT EXISTS bioguide_id TEXT;
ALTER TABLE senators ADD COLUMN IF NOT EXISTS senate_class TEXT;
ALTER TABLE senators ADD COLUMN IF NOT EXISTS first_term_start DATE;
ALTER TABLE senators ADD COLUMN IF NOT EXISTS current_term_end DATE;
ALTER TABLE senators ADD COLUMN IF NOT EXISTS left_date DATE;
ALTER TABLE senators ADD COLUMN IF NOT EXISTS left_reason TEXT;

-- status is 'active' or 'former'. Old rows might have NULL or 'current' from
-- earlier ad-hoc runs; normalize them.
UPDATE senators SET status = 'active' WHERE status IS NULL OR status = 'current';

ALTER TABLE senators
  DROP CONSTRAINT IF EXISTS senators_status_check;
ALTER TABLE senators
  ADD CONSTRAINT senators_status_check CHECK (status IN ('active', 'former'));

CREATE INDEX IF NOT EXISTS idx_senators_status_chamber
  ON senators(status, chamber);
CREATE INDEX IF NOT EXISTS idx_senators_bioguide
  ON senators(bioguide_id);
