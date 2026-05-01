-- Capitol Releases: brief.quotes for the weekly edition
--
-- Weekly briefs include a "five quotes that defined the week" section.
-- Storing them in a dedicated column (rather than reusing sections[])
-- lets the renderer treat them distinctly and lets the validator enforce
-- that every quote is grounded in a release_id from the source set.
--
-- Daily briefs leave this null. Idempotent.

ALTER TABLE briefs ADD COLUMN IF NOT EXISTS quotes JSONB;
