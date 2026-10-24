-- Action proposals stop being ephemeral, and gain a link back to the message that caused them.
--
-- TWO REPORTED PROBLEMS, ONE CAUSE.
--
--   1. "the message when user clicked approve or reject should stay permanently"
--      It did not survive a refresh. ChatSessionService said so plainly — "action proposals
--      are ephemeral by design and are not replayed" — so history returned the assistant's
--      text with no proposal attached, and the card simply vanished. A decision a human made
--      and the system acted on left no trace in the conversation where it was made.
--
--   2. "clicking the link from active task or audit trail should go to the particular prompt"
--      There was nothing to go to. action_audit knows its session but not its message, and
--      tasks knew neither the message nor the action that created them — only
--      source_session_id. Both links could land on the conversation and no closer.
--
-- Persisting the proposal fixes both, because the proposal is the thing that sits between a
-- message and a decision. With this row, history can replay the card, the audit trail can
-- name the message, and a task can point at the prompt that produced it.
--
-- WHY A TABLE RATHER THAN A COLUMN ON messages: a single assistant reply may carry more than
-- one proposal, and the action id has to be the key because action_audit already references
-- it. A JSON column on messages would make "find the proposal for this action id" a scan.

CREATE TABLE action_proposals (
    -- The same opaque string the model's proposal carried and action_audit records against.
    -- PRIMARY KEY, not a surrogate: the id IS the identity, and two rows for one proposal is
    -- the bug V20 spent a migration eliminating one table over.
    action_id   VARCHAR(255) PRIMARY KEY,

    -- CASCADE on both. A proposal is part of the conversation that produced it: delete the
    -- message or the session and the proposal is meaningless. This is the opposite of
    -- action_audit, which is RESTRICT-like by intent — the audit is a record of what a human
    -- decided and must outlive the chat. Same shape, opposite answer, deliberately.
    message_id  UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    session_id  UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,

    type        VARCHAR(50) NOT NULL,

    -- The label as the proposer produced it, stored rather than re-derived. Re-deriving on
    -- read would let the stored proposal drift from the one the user actually saw and
    -- decided on, which is precisely what an audit-adjacent record must not do.
    label       TEXT NOT NULL,

    -- The payload JSON exactly as it was sent to the client. Same reasoning as
    -- action_audit.result: what is wanted back is the bytes the client had.
    payload     TEXT NOT NULL,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_action_proposal_type
        CHECK (type IN ('create-task', 'summarize-document', 'lookup-knowledge'))
);

-- History replay loads every proposal for a page of messages at once. Without this it is a
-- sequential scan per message, which is the N+1 the pagination work on Day 19 existed to kill.
CREATE INDEX idx_action_proposals_message ON action_proposals (message_id);

-- The audit trail resolves its deep link through session, not message.
CREATE INDEX idx_action_proposals_session ON action_proposals (session_id);

-- WHICH ACTION CREATED THIS TASK. Nullable: tasks created before this migration genuinely
-- have no originating action recorded, and inventing one would be a lie in the one table a
-- user manages by hand. Those rows keep linking to their session and no further.
--
-- No foreign key to action_proposals on purpose. A task must survive the deletion of the
-- chat that proposed it — it is the user's work item, not a transcript artefact — and a FK
-- with CASCADE would delete it while ON DELETE SET NULL would quietly erase provenance.
ALTER TABLE tasks ADD COLUMN source_action_id VARCHAR(255);

COMMENT ON TABLE  action_proposals IS 'What the model proposed, kept so history can replay the decision and links can reach the exact message.';
COMMENT ON COLUMN action_proposals.payload IS 'Payload JSON exactly as sent to the client.';
COMMENT ON COLUMN tasks.source_action_id IS 'The action that created this task. NULL for tasks predating V23, and for tasks created by hand.';
