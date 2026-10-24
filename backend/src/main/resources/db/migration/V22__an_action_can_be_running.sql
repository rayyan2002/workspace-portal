-- A decision is recorded instantly; the work it causes may take minutes.
--
-- WHY. V21 stored the OUTCOME of an action, which stopped a navigated-away approve from
-- destroying two minutes of work. It did not fix the thing that made people navigate away:
-- POST /api/ai/actions ran the whole summarise INSIDE the request, so the card sat on a
-- spinner for 78-135 seconds before the human's own decision was acknowledged.
--
-- Creating a task is instant and a rejection is instant. Summarising is not, and it is slow
-- by nature — it runs a full grounded-answer pass over a language model. The decision and
-- the work are separate events and the request should only wait for the first.
--
-- So an approved slow action now returns `running` immediately and finishes in the
-- background, writing its result back to this row. The audit trail then tells the truth at
-- every moment rather than only at the end:
--
--     approved -> running -> completed
--     approved -> running -> failed
--
-- WITHOUT THIS VALUE the in-flight state has nowhere to live, and an approved action would
-- be invisible between the click and the result — the same confusion in a new place.

ALTER TABLE action_audit DROP CONSTRAINT chk_action_audit_status;

ALTER TABLE action_audit
    ADD CONSTRAINT chk_action_audit_status
    CHECK (status IS NULL OR status IN ('completed', 'rejected', 'failed', 'running'));

-- The result and failure_reason constraints from V21 still hold and are deliberately NOT
-- widened: a `running` row has neither yet, which those CHECKs already permit (both are
-- conditional on the terminal status, and NULL satisfies them).

COMMENT ON COLUMN action_audit.status IS
    'What EXECUTION is doing: running while a slow action is in flight, then completed or failed. NULL for rows written before V21.';
