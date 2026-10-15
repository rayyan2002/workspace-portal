CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL, -- TODO: Store securely hashed passwords via Spring Security on Day 5, never plaintext
    name VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);