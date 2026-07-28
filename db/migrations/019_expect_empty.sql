-- 019_expect_empty.sql
--
-- Promote `expect_empty` from seed JSON to a real column.
--
-- A source that legitimately publishes nothing is a normal state, not a
-- failure: Sen. Armstrong (OK) has never posted a release, and 13 state
-- sources were verified on 2026-07-28 to run a clean collector against an
-- empty pressroom. The collectors already honour this -- they suppress
-- "no items found" when the seed says so -- but the flag lived only in
-- seed JSON, so nothing that queries the database could see it.
--
-- That blind spot produced a real wrong answer. Counting empty sources
-- straight from the database made the state tier look 8.3% broken when
-- every one of its empty sources was documented and deliberate. Any SQL
-- check that wants to exclude expected-empty sources currently has to
-- hardcode a list -- test_data_quality already carries
-- `_EXEMPT_PARITY = {"armstrong-alan"}` -- and a hardcoded list drifts
-- the moment a new source is marked in the seeds.
--
-- The reason string is stored alongside the flag on purpose. "This source
-- is expected to be empty" is a claim about the world, and the archive's
-- provenance rule applies to it as much as to a date: state why, so the
-- claim can be re-checked when a chamber reconvenes.

ALTER TABLE officials
    ADD COLUMN IF NOT EXISTS expect_empty BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS expect_empty_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_officials_expect_empty
    ON officials (expect_empty)
    WHERE expect_empty;

COMMENT ON COLUMN officials.expect_empty IS
    'Source verified to publish nothing; zero records is expected, not a failure.';
COMMENT ON COLUMN officials.expect_empty_reason IS
    'Why this source is expected to be empty, and when that was verified.';
