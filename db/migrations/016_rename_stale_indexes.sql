-- Capitol Releases: rename stale senators_* indexes to officials_*
--
-- Cosmetic cleanup. Postgres doesn't auto-rename indexes when their
-- parent table renames, so after migration 012 the indexes still carry
-- the legacy "senators_" prefix even though they live on the officials
-- table. This migration brings the names in line with the table they
-- belong to. Idempotent.

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'senators_pkey') THEN
    EXECUTE 'ALTER INDEX senators_pkey RENAME TO officials_pkey';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_senators_bioguide_id') THEN
    EXECUTE 'ALTER INDEX uq_senators_bioguide_id RENAME TO uq_officials_bioguide_id';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_senators_chamber') THEN
    EXECUTE 'ALTER INDEX idx_senators_chamber RENAME TO idx_officials_chamber';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_senators_state_chamber_district') THEN
    EXECUTE 'ALTER INDEX idx_senators_state_chamber_district RENAME TO idx_officials_state_chamber_district';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_senators_status_chamber') THEN
    EXECUTE 'ALTER INDEX idx_senators_status_chamber RENAME TO idx_officials_status_chamber';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_senators_bioguide') THEN
    EXECUTE 'ALTER INDEX idx_senators_bioguide RENAME TO idx_officials_bioguide';
  END IF;
END$$;
