-- V12__reseed_second_user_demo_data.sql
--
-- Restores user B's demo rows after they were deleted through the new
-- DELETE /api/chat/sessions/{id} endpoint while verifying it.
--
-- V9 cannot simply be re-run: Flyway checksums applied migrations, and editing one
-- that has already run is how you corrupt a schema history. So this is a separate,
-- IDEMPOTENT migration — ON CONFLICT DO NOTHING means it restores the rows on this
-- database and is a harmless no-op on a fresh one where V9 already inserted them.
--
-- The wider lesson: demo data that a demo can destroy needs a repeatable way back.
-- The boundary demonstration (log in as A and B side by side) is only as durable as
-- B's data, and that data is now deletable by design.

INSERT INTO chat_sessions (id, user_id, title, last_message_preview) VALUES
('88888888-8888-8888-8888-888888888881', '99999999-9999-9999-9999-999999999999', 'Other User Private Session', 'This must never appear in user A''s session list.')
ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, session_id, content, sender) VALUES
('88888888-8888-8888-8888-888888888891', '88888888-8888-8888-8888-888888888881', 'Private question from the other user.', 'user'),
('88888888-8888-8888-8888-888888888892', '88888888-8888-8888-8888-888888888881', 'Private answer for the other user.', 'assistant')
ON CONFLICT (id) DO NOTHING;

INSERT INTO tasks (id, title, priority, status, source_session_id) VALUES
('88888888-8888-8888-8888-888888888882', 'Other user private task', 'low', 'todo', '88888888-8888-8888-8888-888888888881')
ON CONFLICT (id) DO NOTHING;

INSERT INTO action_audit (id, action_id, session_id, type, decision) VALUES
('88888888-8888-8888-8888-888888888883', 'act-other-1', '88888888-8888-8888-8888-888888888881', 'create-task', 'approved')
ON CONFLICT (id) DO NOTHING;
