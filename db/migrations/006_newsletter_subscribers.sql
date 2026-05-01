-- Capitol Releases: newsletter subscribers
--
-- Lightweight subscription list for the daily AI brief email. Emails are
-- stored lowercased; unsubscribe_token is a UUID surfaced in every email's
-- one-click unsubscribe link. status transitions: active -> unsubscribed
-- (user action) or active -> bounced (mailer feedback). We never delete
-- rows so a re-subscribe is an UPDATE, preserving the original token.

CREATE TABLE IF NOT EXISTS newsletter_subscribers (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email               TEXT NOT NULL UNIQUE,
  status              TEXT NOT NULL DEFAULT 'active',
  unsubscribe_token   UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
  subscribed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  unsubscribed_at     TIMESTAMPTZ,
  last_sent_brief_id  UUID REFERENCES briefs(id),
  last_sent_at        TIMESTAMPTZ,
  source              TEXT,
  CONSTRAINT subscribers_status_check CHECK (status IN ('active', 'unsubscribed', 'bounced'))
);

CREATE INDEX IF NOT EXISTS idx_subscribers_status
  ON newsletter_subscribers(status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_subscribers_token
  ON newsletter_subscribers(unsubscribe_token);
