-- V11__create_refresh_tokens.sql
--
-- Refresh tokens are deliberately NOT JWTs. A JWT cannot be revoked without a
-- server-side blocklist, which defeats the point of using one; an opaque random token
-- with a database row gives real logout and real rotation.
--
-- Only the SHA-256 hash of the token is stored, for the same reason passwords are
-- hashed: a leak of this table must not hand out usable credentials.

CREATE TABLE refresh_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
