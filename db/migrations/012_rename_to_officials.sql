-- Capitol Releases: rename senators -> officials + structural columns
--
-- Phase 1 of the schema-correctness migration kicked off 2026-05-02 PM EDT,
-- after House wave-2 backfill exposed how badly the legacy table name fits
-- the realized goal (executives, House, state legislatures, future judges).
--
-- This migration:
--   1. Renames table senators -> officials (table name only; column names
--      stay as-is for now; senator_id is column-renamed in a separate
--      atomic-codemod migration once frontend + pipeline have been swept).
--   2. Adds five structural columns:
--         branch         legislative | executive
--         jurisdiction   us | tx | ca | ne | oh | mo | wv | ...
--         office_type    senator | representative | governor | president | ...
--         openstates_id  for state legislators (matches Open States project)
--         external_ids   jsonb catch-all for future ID systems
--   3. Backfills the structural columns from current chamber values:
--         chamber='senate'         -> branch='legislative', jurisdiction='us', office_type='senator', chamber stays 'senate'
--         chamber='house'          -> branch='legislative', jurisdiction='us', office_type='representative', chamber stays 'house'
--         chamber='tx_senate'      -> branch='legislative', jurisdiction='tx', office_type='state_senator', chamber='senate'
--         chamber='ca_senate'      -> branch='legislative', jurisdiction='ca', office_type='state_senator', chamber='senate'
--         chamber='oh_senate'      -> branch='legislative', jurisdiction='oh', office_type='state_senator', chamber='senate'
--         chamber='mo_senate'      -> branch='legislative', jurisdiction='mo', office_type='state_senator', chamber='senate'
--         chamber='ne_unicameral'  -> branch='legislative', jurisdiction='ne', office_type='state_senator', chamber='unicameral'
--         chamber='wv_legislature' -> branch='legislative', jurisdiction='wv', office_type='state_senator', chamber='senate'
--         chamber='executive'      -> branch='executive',   jurisdiction='us', office_type='executive_office', chamber=NULL
--   4. Creates compat view `senators` so legacy SELECT * FROM senators
--      keeps working during the codemod sweep. Drop it once all callers are
--      on `officials`.
--
-- Idempotent. Safe to re-run.

-- Step 1: structural columns (additive, zero risk)
ALTER TABLE senators ADD COLUMN IF NOT EXISTS branch TEXT;
ALTER TABLE senators ADD COLUMN IF NOT EXISTS jurisdiction TEXT;
ALTER TABLE senators ADD COLUMN IF NOT EXISTS office_type TEXT;
ALTER TABLE senators ADD COLUMN IF NOT EXISTS openstates_id TEXT;
ALTER TABLE senators ADD COLUMN IF NOT EXISTS external_ids JSONB;

-- Step 1.5: relax chamber NOT NULL — executives correctly have no chamber.
-- The legacy default 'senate' was a hack to satisfy the constraint when
-- adding the White House row earlier; with branch='executive' available
-- as the proper member-type signal, chamber can be NULL for non-legislators.
ALTER TABLE senators ALTER COLUMN chamber DROP NOT NULL;
ALTER TABLE senators ALTER COLUMN chamber DROP DEFAULT;

-- Step 2: backfill from current chamber values
UPDATE senators SET
  branch       = 'legislative',
  jurisdiction = 'us',
  office_type  = 'senator'
WHERE chamber = 'senate' AND (branch IS NULL OR jurisdiction IS NULL);

UPDATE senators SET
  branch       = 'legislative',
  jurisdiction = 'us',
  office_type  = 'representative'
WHERE chamber = 'house' AND (branch IS NULL OR jurisdiction IS NULL);

UPDATE senators SET
  branch       = 'legislative',
  jurisdiction = 'tx',
  office_type  = 'state_senator',
  chamber      = 'senate'
WHERE chamber = 'tx_senate';

UPDATE senators SET
  branch       = 'legislative',
  jurisdiction = 'ca',
  office_type  = 'state_senator',
  chamber      = 'senate'
WHERE chamber = 'ca_senate';

UPDATE senators SET
  branch       = 'legislative',
  jurisdiction = 'oh',
  office_type  = 'state_senator',
  chamber      = 'senate'
WHERE chamber = 'oh_senate';

UPDATE senators SET
  branch       = 'legislative',
  jurisdiction = 'mo',
  office_type  = 'state_senator',
  chamber      = 'senate'
WHERE chamber = 'mo_senate';

UPDATE senators SET
  branch       = 'legislative',
  jurisdiction = 'ne',
  office_type  = 'state_senator',
  chamber      = 'unicameral'
WHERE chamber = 'ne_unicameral';

UPDATE senators SET
  branch       = 'legislative',
  jurisdiction = 'wv',
  office_type  = 'state_senator',
  chamber      = 'senate'
WHERE chamber = 'wv_legislature';

UPDATE senators SET
  branch       = 'executive',
  jurisdiction = 'us',
  office_type  = 'executive_office',
  chamber      = NULL
WHERE chamber = 'executive';

-- Step 3: rename table senators -> officials (idempotent guard)
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
    EXECUTE 'ALTER TABLE senators RENAME TO officials';
  END IF;
END$$;

-- Step 4: indexes for the structural columns
CREATE INDEX IF NOT EXISTS idx_officials_jurisdiction_chamber
  ON officials(jurisdiction, chamber, status);
CREATE INDEX IF NOT EXISTS idx_officials_branch_jurisdiction
  ON officials(branch, jurisdiction);
CREATE INDEX IF NOT EXISTS idx_officials_office_type
  ON officials(office_type);

-- Step 5: compatibility view so legacy `FROM senators` callers keep working
-- during the codemod sweep. Drop in a future migration once code is clean.
DROP VIEW IF EXISTS senators;
CREATE VIEW senators AS SELECT * FROM officials;

-- Step 6: NOT NULL constraints on the new structural columns once backfill
-- is verified complete. Done as a separate ALTER so the UPDATEs above can
-- complete first.
ALTER TABLE officials
  ALTER COLUMN branch       SET NOT NULL,
  ALTER COLUMN jurisdiction SET NOT NULL,
  ALTER COLUMN office_type  SET NOT NULL;
