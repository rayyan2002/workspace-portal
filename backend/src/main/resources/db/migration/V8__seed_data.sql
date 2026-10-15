-- V8__seed_data.sql

-- 1. Demo User
-- UUID: 11111111-1111-1111-1111-111111111111
-- Password is the exact bcrypt hash for 'securepassword123'
INSERT INTO users (id, email, password, name) VALUES
('11111111-1111-1111-1111-111111111111', 'user@bluestone.com', '$2a$10$jeE4v1hyIWHPUzqkeIK/Eetve0NuqwqlMKAQxrWCzX1boVpFC8Jo6', 'Muhammad Rayyan Ayub');

-- 2. Documents (Matching the frontend mock catalog)
INSERT INTO documents (id, filename, size_bytes, status) VALUES
('22222222-2222-2222-2222-222222222221', 'maintenance_log_Q2.md', 10240, 'ready'),
('22222222-2222-2222-2222-222222222222', 'FastAPI_Proxy_Architecture.md', 25600, 'ready'),
('22222222-2222-2222-2222-222222222223', 'aerotwin_telemetry_spec_v2.pdf', 1512000, 'processing'),
('22222222-2222-2222-2222-222222222224', 'quarterly_financial_report.pdf', 2048576, 'ready');

-- 3. Chat Session
INSERT INTO chat_sessions (id, user_id, title, last_message_preview) VALUES
('33333333-3333-3333-3333-333333333333', '11111111-1111-1111-1111-111111111111', 'Airport Operations Review', 'Here is the summary of the flight schedule...');

-- 4. Messages (One User query, one Assistant response)
INSERT INTO messages (id, session_id, content, sender) VALUES
('44444444-4444-4444-4444-444444444441', '33333333-3333-3333-3333-333333333333', 'Can you summarize the airport flight schedule?', 'user'),
('44444444-4444-4444-4444-444444444442', '33333333-3333-3333-3333-333333333333', 'Here is the summary of the flight schedule with runway efficiency metrics.', 'assistant');

-- 5. Tasks (Linked to the chat session)
INSERT INTO tasks (id, title, priority, status, source_session_id) VALUES
('55555555-5555-5555-5555-555555555555', 'Review runway schedule', 'high', 'todo', '33333333-3333-3333-3333-333333333333');

-- 6. Citations (Linking the assistant message to the financial report)
INSERT INTO citations (id, message_id, document_id, section, excerpt) VALUES
('66666666-6666-6666-6666-666666666666', '44444444-4444-4444-4444-444444444442', '22222222-2222-2222-2222-222222222224', 'Executive Summary', '...runway efficiency metrics...');

-- 7. Action Audit (Governance log for the created task)
INSERT INTO action_audit (id, action_id, session_id, type, decision) VALUES
('77777777-7777-7777-7777-777777777777', 'act-98765-1', '33333333-3333-3333-3333-333333333333', 'create-task', 'approved');
