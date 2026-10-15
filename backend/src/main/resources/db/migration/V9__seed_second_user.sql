-- V9__seed_second_user.sql
--
-- A second user exists purely so authorization boundaries are TESTABLE.
-- With one seeded user, findAll() and findByOwner() return identical results and
-- every scoping assertion passes for the wrong reason (the Day-8 lesson).
-- User B owns their own session, messages, and task, so "A sees 1 session, not 2"
-- and "A PATCHing B's task -> 404" are real assertions.

-- 1. Second user (same bcrypt hash as user A: password is 'securepassword123')
INSERT INTO users (id, email, password, name) VALUES
('99999999-9999-9999-9999-999999999999', 'other@example.com', '$2a$10$jeE4v1hyIWHPUzqkeIK/Eetve0NuqwqlMKAQxrWCzX1boVpFC8Jo6', 'Other User');

-- 2. User B's own chat session
INSERT INTO chat_sessions (id, user_id, title, last_message_preview) VALUES
('88888888-8888-8888-8888-888888888881', '99999999-9999-9999-9999-999999999999', 'Other User Private Session', 'This must never appear in user A''s session list.');

-- 3. User B's messages
INSERT INTO messages (id, session_id, content, sender) VALUES
('88888888-8888-8888-8888-888888888891', '88888888-8888-8888-8888-888888888881', 'Private question from the other user.', 'user'),
('88888888-8888-8888-8888-888888888892', '88888888-8888-8888-8888-888888888881', 'Private answer for the other user.', 'assistant');

-- 4. User B's task (reachable only via their session)
INSERT INTO tasks (id, title, priority, status, source_session_id) VALUES
('88888888-8888-8888-8888-888888888882', 'Other user private task', 'low', 'todo', '88888888-8888-8888-8888-888888888881');

-- 5. User B's action audit row
INSERT INTO action_audit (id, action_id, session_id, type, decision) VALUES
('88888888-8888-8888-8888-888888888883', 'act-other-1', '88888888-8888-8888-8888-888888888881', 'create-task', 'approved');
