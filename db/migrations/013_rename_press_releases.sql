-- Capitol Releases: rename press_releases -> official_site_items
--
-- Phase 2 of the schema-correctness migration (2026-05-02 PM EDT). The
-- press_releases table holds *all* original content scraped from official
-- .gov member websites: press releases, statements, op-eds, blog posts,
-- newsletters, floor statements, letters. Naming it press_releases is a
-- legacy artifact from when the project was Senate-only and press releases
-- were the only content type. The content_type column has been doing the
-- real classification work for months.
--
-- Social posts (Bluesky) and floor speeches (Congressional Record) live
-- in their own tables (social_posts, floor_speeches) because they have
-- different shapes. So this table is specifically "items scraped from
-- the official's website" — official_site_items captures that scope.
--
-- A unified search/feed surface across all three content tables can come
-- later as a view (e.g. search_documents UNION ALL of all three).
--
-- This migration:
--   1. Renames table press_releases -> official_site_items (table only;
--      column names — including senator_id — stay as-is for now).
--   2. Renames the FK index on content_versions.press_release_id ->
--      content_versions.press_release_id (logical column unchanged but
--      the underlying constraint reference travels with the rename).
--   3. Creates compat VIEW press_releases aliasing official_site_items
--      so legacy code paths keep working during the codemod sweep.
--
-- Idempotent. Safe to re-run.

-- Step 1: rename the table (idempotent guard)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'press_releases'
      AND table_type = 'BASE TABLE'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'official_site_items'
      AND table_type = 'BASE TABLE'
  ) THEN
    EXECUTE 'ALTER TABLE press_releases RENAME TO official_site_items';
  END IF;
END$$;

-- Step 2: compatibility view so legacy `FROM press_releases` callers
-- keep working during the codemod sweep. Drop this in a future migration
-- once all callers have moved to official_site_items.
--
-- Idempotent across migration order: 014 will later rename the FK column
-- from senator_id to official_id and recreate this view with the
-- `official_id AS senator_id` alias. If a re-run of THIS migration
-- follows 014, we'd otherwise wipe that alias and break unswept SELECT
-- callers. Detect post-014 state by checking column shape and create
-- the right view form for whichever state we're in.
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
    -- 014 has already run: column is named official_id; expose senator_id
    -- as a legacy alias so unswept SELECTs keep working.
    EXECUTE 'CREATE VIEW press_releases AS '
            'SELECT *, official_id AS senator_id FROM official_site_items';
  ELSE
    -- 014 hasn't run yet: column is still senator_id; simple alias view.
    EXECUTE 'CREATE VIEW press_releases AS SELECT * FROM official_site_items';
  END IF;
END$$;
