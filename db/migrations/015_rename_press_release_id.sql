-- Capitol Releases: rename content_versions.press_release_id -> official_site_item_id
--
-- Phase 3 step 4 (2026-05-02 PM EDT). Final FK column rename — the
-- press_release_id name was a parallel legacy artifact alongside
-- senator_id. Renames it to match the now-canonical
-- official_site_items table name.
--
-- Idempotent.

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='content_versions'
               AND column_name='press_release_id') THEN
    EXECUTE 'ALTER TABLE content_versions RENAME COLUMN press_release_id TO official_site_item_id';
  END IF;
END$$;
