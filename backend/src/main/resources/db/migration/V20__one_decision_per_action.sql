-- Month 3 Day 11 — a proposal can be decided exactly once.
--
-- action_audit had a CHECK on `type`, a CHECK on `decision`, a primary key on `id` and a
-- foreign key to chat_sessions. It had NOTHING on action_id, so the same proposal could be
-- decided any number of times and every approval executed again.
--
-- That is not hypothetical. This database already contained:
--
--     act-123          approved + approved    two tasks from one proposal
--     act-d1ed2401...  approved + approved
--     act-fa23f0bb...  rejected + approved    a human declined it; it ran anyway
--     act-4ef90695...  approved + rejected
--     act-739a29e5...  approved + rejected
--
-- and duplicate task rows to match ("Review runway schedule" three times). A double-click,
-- a retried request, or a browser back-button was enough.
--
-- The `rejected + approved` row is the worst of the five. Rejection is a human declining an
-- action, and nothing prevented the same action being approved afterwards.

-- 1. Keep the FIRST decision for each action and delete the rest.
--
--    First, not last, and deliberately: the earliest row is the decision the human actually
--    made on the control in front of them. Every later row is a repeat this constraint now
--    makes impossible, and in the `rejected + approved` case the first decision is the
--    refusal — which is the one that must survive.
--
--    The duplicate audit rows are deleted; any task rows they caused are NOT. Those are real
--    rows a user can see, and silently deleting task history to tidy up an audit table would
--    be a worse lie than the duplicates. They stay, and this migration is the record of why
--    they exist.
DELETE FROM action_audit a
USING action_audit keep
WHERE a.action_id = keep.action_id
  AND (keep.created_at < a.created_at
       OR (keep.created_at = a.created_at AND keep.id < a.id));

-- 2. Make a second decision impossible rather than merely unlikely.
--
--    A UNIQUE constraint, not application-level checking: the audit row is written BEFORE
--    execution, so the database refusing the insert means the side effect never happens.
--    That ordering was incidental before and is now load-bearing.
ALTER TABLE action_audit
    ADD CONSTRAINT uq_action_audit_action_id UNIQUE (action_id);

COMMENT ON CONSTRAINT uq_action_audit_action_id ON action_audit IS
    'One decision per proposal. Written before execution, so a duplicate insert prevents a duplicate side effect.';
