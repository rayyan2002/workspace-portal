CREATE TABLE action_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_id VARCHAR(255) NOT NULL,
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL CHECK (type IN ('create-task', 'summarize-document', 'lookup-knowledge')),
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('approved', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);