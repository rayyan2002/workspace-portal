-- V16__retire_demo_accounts.sql
--
-- Retires the seeded demo accounts, whose password is published in V8 and was until
-- now printed on the login screen.
--
-- Deleting them outright would have destroyed real work: user@example.com had
-- accumulated genuinely uploaded documents, chat history, and tasks, and held the only
-- ROLE_ADMIN. So its content is transferred to the real account first.
--
-- On a FRESH database this migration is what makes the demo accounts not exist: V8/V9
-- create them, this deletes them, and the transfer below simply matches nothing because
-- the real account is not there either. V8 itself is left untouched — editing an applied
-- migration breaks its checksum and corrupts the schema history.

DO $$
DECLARE
    demo_a  UUID := '11111111-1111-1111-1111-111111111111';  -- user@example.com
    demo_b  UUID := '99999999-9999-9999-9999-999999999999';  -- other@example.com
    heir    UUID;
    admin   UUID;
BEGIN
    SELECT id INTO heir FROM users WHERE email = 'mayub@nisum.com';

    IF heir IS NOT NULL THEN
        -- Documents and chat sessions carry ownership directly. Everything else
        -- follows them: messages, tasks and audit rows hang off the session, and
        -- citations hang off the message and document.
        UPDATE documents     SET owner_id = heir WHERE owner_id = demo_a;
        UPDATE chat_sessions SET user_id  = heir WHERE user_id  = demo_a;

        -- The heir inherits admin, or nothing would be left that can reach
        -- /api/admin/**.
        SELECT id INTO admin FROM roles WHERE name = 'ROLE_ADMIN';
        INSERT INTO user_roles (user_id, role_id)
        VALUES (heir, admin)
        ON CONFLICT DO NOTHING;
    END IF;

    -- citations.document_id is ON DELETE RESTRICT, so any citation still pointing at a
    -- document about to disappear would abort the whole delete. Anything left here
    -- belongs to demo_b, whose documents are going with it.
    DELETE FROM citations
    WHERE document_id IN (SELECT id FROM documents WHERE owner_id IN (demo_a, demo_b));

    -- Everything else cascades from users: sessions, messages, tasks, audit rows,
    -- documents, refresh tokens, reset tokens, role assignments.
    DELETE FROM users WHERE id IN (demo_a, demo_b);
END $$;
