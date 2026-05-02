-- Capitol Releases: rename senators -> officials + structural columns
--
-- Phase 1 of the schema-correctness migration kicked off 2026-05-02 PM EDT,
-- after House wave-2 backfill exposed how badly the legacy table name fits
-- the realized goal (executives, House, state legislatures, future judges).
--
-- This migration:
--   1. Renames table senators -> officials FIRST (idempotent guard) so
--      subsequent ALTERs operate on the canonical name regardless of
--      whether the migration is running first-time or being re-run after
--      `senators` has already become a view.
--   2. Adds five structural columns:
--         branch         legislative | executive
--         jurisdiction   us | tx | ca | ne | oh | mo | wv | ...
--         office_type    senator | representative | governor | president | ...
--         openstates_id  for state legislators (matches Open States project)
--         external_ids   jsonb catch-all for future ID systems
--   3. Drops the chamber NOT NULL — executives correctly have no chamber.
--   4. Backfills the structural columns from current chamber values.
--      Normalizes chamber: tx_senate / ca_senate / oh_senate / mo_senate /
--      wv_legislature -> 'senate', ne_unicameral -> 'unicameral',
--      executive -> NULL.
--   5. Adds NOT NULL constraints once backfill is verified.
--   6. Creates compat view `senators` so legacy SELECT * FROM senators
--      keeps working during the codemod sweep. Drop in a future migration
--      once all callers are on `officials`.
--
-- Idempotent. Safe to re-run. Each ALTER uses IF [NOT] EXISTS or operates
-- on `officials` (the canonical name post-rename) so a second run is a
-- harmless no-op.

-- Step 1: rename table senators -> officials (idempotent guard).
-- Done first so all subsequent ALTERs operate on the canonical name.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'senators'
      AND table_type = 'BASE TABLE'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'officials'
      AND table_type = 'BASE TABLE'
  ) THEN
    -- Drop any existing senators view from a partial earlier run.
    EXECUTE 'DROP VIEW IF EXISTS senators';
    EXECUTE 'ALTER TABLE senators RENAME TO officials';
  END IF;
END$$;

-- Step 2: structural columns (additive, idempotent on `officials`)
ALTER TABLE officials ADD COLUMN IF NOT EXISTS branch        TEXT;
ALTER TABLE officials ADD COLUMN IF NOT EXISTS jurisdiction  TEXT;
ALTER TABLE officials ADD COLUMN IF NOT EXISTS office_type   TEXT;
ALTER TABLE officials ADD COLUMN IF NOT EXISTS openstates_id TEXT;
ALTER TABLE officials ADD COLUMN IF NOT EXISTS external_ids  JSONB;

-- Step 3: relax chamber NOT NULL — executives correctly have no chamber.
ALTER TABLE officials ALTER COLUMN chamber DROP NOT NULL;
ALTER TABLE officials ALTER COLUMN chamber DROP DEFAULT;

-- Step 4: backfill structural columns from current chamber values.
-- Each UPDATE is idempotent (re-runs are no-ops once values are set).
UPDATE officials SET
  branch       = 'legislative',
  jurisdiction = 'us',
  office_type  = 'senator'
WHERE chamber = 'senate' AND (branch IS NULL OR jurisdiction IS NULL);

UPDATE officials SET
  branch       = 'legislative',
  jurisdiction = 'us',
  office_type  = 'representative'
WHERE chamber = 'house' AND (branch IS NULL OR jurisdiction IS NULL);

UPDATE officials SET
  branch       = 'legislative',
  jurisdiction = 'tx',
  office_type  = 'state_senator',
  chamber      = 'senate'
WHERE chamber = 'tx_senate';

UPDATE officials SET
  branch       = 'legislative',
  jurisdiction = 'ca',
  office_type  = 'state_senator',
  chamber      = 'senate'
WHERE chamber = 'ca_senate';

UPDATE officials SET
  branch       = 'legislative',
  jurisdiction = 'oh',
  office_type  = 'state_senator',
  chamber      = 'senate'
WHERE chamber = 'oh_senate';

UPDATE officials SET
  branch       = 'legislative',
  jurisdiction = 'mo',
  office_type  = 'state_senator',
  chamber      = 'senate'
WHERE chamber = 'mo_senate';

UPDATE officials SET
  branch       = 'legislative',
  jurisdiction = 'ne',
  office_type  = 'state_senator',
  chamber      = 'unicameral'
WHERE chamber = 'ne_unicameral';

UPDATE officials SET
  branch       = 'legislative',
  jurisdiction = 'wv',
  office_type  = 'state_senator',
  chamber      = 'senate'
WHERE chamber = 'wv_legislature';

UPDATE officials SET
  branch       = 'executive',
  jurisdiction = 'us',
  office_type  = 'executive_office',
  chamber      = NULL
WHERE chamber = 'executive';

-- Step 5: indexes for the structural columns
CREATE INDEX IF NOT EXISTS idx_officials_jurisdiction_chamber
  ON officials(jurisdiction, chamber, status);
CREATE INDEX IF NOT EXISTS idx_officials_branch_jurisdiction
  ON officials(branch, jurisdiction);
CREATE INDEX IF NOT EXISTS idx_officials_office_type
  ON officials(office_type);

-- Step 6: NOT NULL constraints on the structural columns.
-- Skip if already NOT NULL (re-running this migration is a no-op).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='officials' AND column_name='branch'
               AND is_nullable='YES') THEN
    EXECUTE 'ALTER TABLE officials ALTER COLUMN branch SET NOT NULL';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='officials' AND column_name='jurisdiction'
               AND is_nullable='YES') THEN
    EXECUTE 'ALTER TABLE officials ALTER COLUMN jurisdiction SET NOT NULL';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='officials' AND column_name='office_type'
               AND is_nullable='YES') THEN
    EXECUTE 'ALTER TABLE officials ALTER COLUMN office_type SET NOT NULL';
  END IF;
END$$;

-- Step 7: compatibility view so legacy `FROM senators` callers keep
-- working during the codemod sweep. Drop in a future migration once
-- code is clean.
DROP VIEW IF EXISTS senators;
CREATE VIEW senators AS SELECT * FROM officials;
