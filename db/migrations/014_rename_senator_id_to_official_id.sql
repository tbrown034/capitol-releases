-- Capitol Releases: rename senator_id -> official_id across content tables
--
-- Phase 3 step 3 of the schema-correctness migration (2026-05-02 PM EDT).
-- Closes out the half-state left by migrations 012 + 013 — the tables are
-- named correctly (officials, official_site_items) but the FK columns
-- still carry the legacy "senator_id" name even on rows for House
-- representatives, executives, and state senators where it's actively
-- misleading.
--
-- Renames:
--   official_site_items.senator_id -> official_id
--   social_posts.senator_id        -> official_id
--   floor_speeches.senator_id      -> official_id
--   alerts.senator_id              -> official_id
--   health_checks.senator_id       -> official_id
--
-- The accompanying code sweep updates all references in pipeline/ and
-- app/ to use official_id. Compat views are extended to alias
-- official_id back to senator_id for any callers that haven't been
-- swept yet (read-only — INSERTs must target the underlying table
-- using official_id).
--
-- Idempotent: each rename is guarded so re-runs are no-ops.

DO $$
BEGIN
  -- official_site_items
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='official_site_items' AND column_name='senator_id') THEN
    EXECUTE 'ALTER TABLE official_site_items RENAME COLUMN senator_id TO official_id';
  END IF;

  -- social_posts
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='social_posts' AND column_name='senator_id') THEN
    EXECUTE 'ALTER TABLE social_posts RENAME COLUMN senator_id TO official_id';
  END IF;

  -- floor_speeches (note: senator_id was nullable here; bioguide_id is
  -- the primary join key for floor speeches, but the senator_id slug
  -- column is also maintained as a convenience.)
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='floor_speeches' AND column_name='senator_id') THEN
    EXECUTE 'ALTER TABLE floor_speeches RENAME COLUMN senator_id TO official_id';
  END IF;

  -- alerts
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='alerts' AND column_name='senator_id') THEN
    EXECUTE 'ALTER TABLE alerts RENAME COLUMN senator_id TO official_id';
  END IF;

  -- health_checks
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='health_checks' AND column_name='senator_id') THEN
    EXECUTE 'ALTER TABLE health_checks RENAME COLUMN senator_id TO official_id';
  END IF;
END$$;

-- Recreate press_releases compat view exposing official_id AND senator_id
-- (alias) so any unswept read paths keep working. Drop in a follow-up
-- migration once the codemod sweep is complete and verified.
--
-- Idempotent: detect column shape and create the right view form. Mirrors
-- the same DO-block in 013 so re-running either migration in any order
-- converges on the right view.
DROP VIEW IF EXISTS press_releases;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'official_site_items'
               AND column_name = 'official_id')
     AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                     WHERE table_name = 'official_site_items'
                       AND column_name = 'senator_id')
  THEN
    EXECUTE 'CREATE VIEW press_releases AS '
            'SELECT *, official_id AS senator_id FROM official_site_items';
  ELSE
    EXECUTE 'CREATE VIEW press_releases AS SELECT * FROM official_site_items';
  END IF;
END$$;
