-- Capitol Releases: auth (Better Auth)
--
-- Four tables managed by Better Auth: user, session, account, verification.
-- Schema mirrors better-auth's drizzle adapter expectations exactly — column
-- names are intentionally camelCase in code (mapped to snake_case here via the
-- drizzle column names) and the four-table shape is fixed by the library.
--
-- Extension: `tier` on user (default 'free') is forward-looking for paid
-- gating of state-level / US-House content. Better Auth picks this up via
-- `user.additionalFields` in lib/auth.ts.
--
-- Idempotent.

CREATE TABLE IF NOT EXISTS "user" (
  id              text PRIMARY KEY,
  name            text NOT NULL,
  email           text NOT NULL UNIQUE,
  email_verified  boolean NOT NULL DEFAULT false,
  image           text,
  tier            text NOT NULL DEFAULT 'free',
  created_at      timestamp NOT NULL DEFAULT now(),
  updated_at      timestamp NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "session" (
  id          text PRIMARY KEY,
  expires_at  timestamp NOT NULL,
  token       text NOT NULL UNIQUE,
  created_at  timestamp NOT NULL DEFAULT now(),
  updated_at  timestamp NOT NULL DEFAULT now(),
  ip_address  text,
  user_agent  text,
  user_id     text NOT NULL REFERENCES "user"(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS session_user_id_idx ON "session"(user_id);

CREATE TABLE IF NOT EXISTS "account" (
  id                         text PRIMARY KEY,
  account_id                 text NOT NULL,
  provider_id                text NOT NULL,
  user_id                    text NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  access_token               text,
  refresh_token              text,
  id_token                   text,
  access_token_expires_at    timestamp,
  refresh_token_expires_at   timestamp,
  scope                      text,
  password                   text,
  created_at                 timestamp NOT NULL DEFAULT now(),
  updated_at                 timestamp NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS account_user_id_idx ON "account"(user_id);

CREATE TABLE IF NOT EXISTS "verification" (
  id          text PRIMARY KEY,
  identifier  text NOT NULL,
  value       text NOT NULL,
  expires_at  timestamp NOT NULL,
  created_at  timestamp NOT NULL DEFAULT now(),
  updated_at  timestamp NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS verification_identifier_idx ON "verification"(identifier);
