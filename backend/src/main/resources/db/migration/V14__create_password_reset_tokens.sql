-- V14__create_password_reset_tokens.sql
--
-- Same reasoning as refresh_tokens: only the SHA-256 hash of the token is stored.
-- A reset token is a temporary credential that can take over an account, so a leak
-- of this table must not hand out working ones.
--
-- Single-use and short-lived: used_at is stamped on redemption so a token cannot be
-- replayed, and expires_at keeps the window small even if a reset email is forwarded
-- or sits in an inbox.

CREATE TABLE password_reset_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_password_reset_tokens_user ON password_reset_tokens(user_id);
