-- V10__create_roles.sql
--
-- Normalized role model rather than a single 'role' column on users: a user can hold
-- more than one role, and adding a role later is an INSERT rather than a schema change.
-- Names carry the ROLE_ prefix because that is the convention Spring Security's
-- hasRole()/@PreAuthorize("hasRole('ADMIN')") expects on the underlying authority.

CREATE TABLE roles (
    id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) NOT NULL UNIQUE CHECK (name IN ('ROLE_USER', 'ROLE_ADMIN'))
);

CREATE TABLE user_roles (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE INDEX idx_user_roles_user ON user_roles(user_id);

INSERT INTO roles (id, name) VALUES
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1', 'ROLE_USER'),
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2', 'ROLE_ADMIN');

-- Every existing user is a plain user...
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1' FROM users u;

-- ...and the primary seeded account is additionally an admin, so role-restricted
-- endpoints have someone who can actually reach them.
INSERT INTO user_roles (user_id, role_id) VALUES
('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2');
