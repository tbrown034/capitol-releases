-- Capitol Releases: daily AI-generated brief
--
-- The brief is a derivative product, never part of the canonical record. It
-- summarizes a day's press releases in journalist-tier voice (modeled on
-- Trevor's Capitol Watch / Democracy Watch newsletters at Oklahoma Watch),
-- always grounded in press_releases.id citations.
--
-- Determinism / provenance principles still apply: model_version pins the
-- exact Claude model, prompt_hash pins the exact prompt that produced the
-- brief, source_release_ids[] pins the exact set of releases the synthesis
-- considered. Re-running with the same inputs produces a new row, not an
-- overwrite (status='draft' is queryable separately from status='published').

CREATE TABLE IF NOT EXISTS briefs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brief_date          DATE NOT NULL,            -- the day being summarized (ET)
  edition             TEXT NOT NULL DEFAULT 'daily', -- daily | weekly_wrap | special
  status              TEXT NOT NULL DEFAULT 'draft', -- draft | published | retracted
  model_version       TEXT NOT NULL,            -- e.g. 'claude-sonnet-4-6'
  prompt_hash         TEXT NOT NULL,            -- SHA-256 of the system+user prompt
  headline            TEXT NOT NULL,
  dek                 TEXT,                     -- one-sentence subhed
  lede                TEXT NOT NULL,            -- opening paragraph(s)
  sections            JSONB NOT NULL,           -- [{theme, body, release_ids[]}]
  signals             JSONB,                    -- volume anomalies, recess context, votes
  silent              JSONB,                    -- senators with no recent releases
  external_context    JSONB,                    -- top external headlines (advisory)
  source_release_ids  UUID[] NOT NULL,          -- every release the model could see
  cited_release_ids   UUID[] NOT NULL,          -- subset actually cited in output
  input_tokens        INTEGER,
  output_tokens       INTEGER,
  cost_usd            NUMERIC(10,6),
  generated_at        TIMESTAMPTZ DEFAULT NOW(),
  published_at        TIMESTAMPTZ,
  retracted_at        TIMESTAMPTZ,
  retracted_reason    TEXT
);

CREATE INDEX IF NOT EXISTS idx_briefs_date_edition
  ON briefs(brief_date DESC, edition);
CREATE INDEX IF NOT EXISTS idx_briefs_status_date
  ON briefs(status, brief_date DESC);

-- Only one published daily brief per date. Drafts are unconstrained so we can
-- regenerate freely during QA.
CREATE UNIQUE INDEX IF NOT EXISTS idx_briefs_published_unique
  ON briefs(brief_date, edition)
  WHERE status = 'published';
