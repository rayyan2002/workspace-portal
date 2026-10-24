-- Keep what an approved action produced, so deciding it again returns the real answer.
--
-- THE REPORTED BUG. Approving a summarize-document action takes about two minutes — one
-- measured run was 134.9 seconds, because it runs a full grounded-answer pass over a
-- language model. The card showed "Processing..." with no timer and no explanation, so the
-- user did the reasonable thing and navigated away. That aborts the request in the browser.
-- The SERVER finished anyway, threw the result on the floor, and when they came back and
-- clicked again the idempotency branch had nothing to return but "already decided".
--
-- Two minutes of work destroyed by a click, and the design said so out loud: V20's comment
-- read "the original side effect is not replayed and its result was never stored, so there
-- is nothing truthful to return here". This is that sentence being fixed rather than
-- apologised for.
--
-- WHY STATUS IS STORED TOO, and this is a second bug rather than bookkeeping. The
-- idempotency branch inferred the status from the DECISION: approved meant completed. But
-- an approved action can FAIL — summarising calls a model over the network — so replaying a
-- failed action reported success. The decision and the outcome are different facts and the
-- table now holds both.
--
-- NULLABLE, all three, and deliberately. Rows decided before this migration genuinely have
-- no stored result; there is no backfill that would not be an invention. ActionService
-- falls back to its previous behaviour for those, so an old proposal still answers
-- "already decided" rather than claiming a summary it never kept.

ALTER TABLE action_audit
    ADD COLUMN status         VARCHAR(20),
    ADD COLUMN result         TEXT,
    ADD COLUMN failure_reason TEXT;

-- The same three values ActionStatus can take. Constrained here for the same reason
-- decision is: a typo in Java should fail on write, not surface months later as a status
-- the frontend has no branch for.
ALTER TABLE action_audit
    ADD CONSTRAINT chk_action_audit_status
    CHECK (status IS NULL OR status IN ('completed', 'rejected', 'failed'));

-- A failure reason without a failure, or a result on a rejection, would mean the writer and
-- the reader disagree about what happened — the exact class of bug this table exists to
-- settle. Cheaper to forbid than to debug.
ALTER TABLE action_audit
    ADD CONSTRAINT chk_action_audit_failure_reason
    CHECK (failure_reason IS NULL OR status = 'failed');

ALTER TABLE action_audit
    ADD CONSTRAINT chk_action_audit_result
    CHECK (result IS NULL OR status = 'completed');

COMMENT ON COLUMN action_audit.status IS
    'What EXECUTION did, as opposed to what the user decided. NULL for rows written before V21.';
COMMENT ON COLUMN action_audit.result IS
    'The result JSON exactly as the API returned it, so a repeated decision replays the answer rather than re-running a two-minute side effect.';
COMMENT ON COLUMN action_audit.failure_reason IS
    'Operator-facing text, never document content. Only present when status is failed.';
