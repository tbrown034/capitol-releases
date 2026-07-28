-- 018_item_mentions.sql
--
-- Per-legislator attribution for caucus-published records.
--
-- Colorado is the first jurisdiction where the publisher of a press release
-- is not a member. All 100 Colorado legislators publish through one of four
-- party caucus organizations, so official_site_items.official_id points at a
-- caucus_pressroom row, not a person. Attribution to people has to be a
-- separate relation, and it has to be many-to-many: measured across 239
-- Colorado Senate Democrats releases from 2026, the mean release names 3.2
-- sitting legislators and only 8% name exactly one.
--
-- `role` records HOW a legislator appears, which is the part a reporter
-- actually cares about:
--   primary    named in the headline, or the bill's named sponsor
--   quoted     carries a direct quotation attributed to them
--   mentioned  named in the body with no quote
--
-- The table is deliberately general (any item, any official) rather than
-- Colorado-specific. The same shape covers congressional committee releases
-- and joint statements when those land -- see GOALS.md "v2 stretch".

CREATE TABLE IF NOT EXISTS item_mentions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id         UUID NOT NULL REFERENCES official_site_items(id) ON DELETE CASCADE,
    official_id     TEXT NOT NULL REFERENCES officials(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('primary', 'quoted', 'mentioned')),
    -- How the name was matched, so a bad rule can be found and re-run later:
    -- 'title_match', 'quote_attribution', 'body_name', 'ai_adjudicated'.
    match_method    TEXT NOT NULL,
    -- The literal string matched in the source text. Kept for auditability:
    -- every attribution claim must be traceable back to the words that
    -- produced it, same as date_source on the item itself.
    matched_text    TEXT,
    confidence      REAL NOT NULL DEFAULT 1.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- One row per (item, official, role). A legislator quoted twice in one
    -- release is one 'quoted' mention, but the same person can legitimately
    -- be both 'primary' and 'quoted'.
    UNIQUE (item_id, official_id, role)
);

CREATE INDEX IF NOT EXISTS idx_item_mentions_official
    ON item_mentions (official_id, role);
CREATE INDEX IF NOT EXISTS idx_item_mentions_item
    ON item_mentions (item_id);

COMMENT ON TABLE item_mentions IS
    'Many-to-many attribution of caucus-published items to individual officials.';
