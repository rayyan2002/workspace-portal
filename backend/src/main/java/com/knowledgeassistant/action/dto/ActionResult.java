package com.knowledgeassistant.action.dto;

import com.knowledgeassistant.action.ActionDecision;
import com.knowledgeassistant.action.ActionStatus;
import com.knowledgeassistant.action.ActionType;

public record ActionResult(
        String actionId,
        ActionStatus status, // 'completed', 'rejected' or 'failed'
        ActionType type,
        Object result, // Can be TaskDto, String, or null

        /**
         * Why the action did not complete. Null unless {@code status} is {@code failed}.
         *
         * <p>Added Day 19 because the UI had nothing to show. A user approved a
         * summarize-document proposal, the execution failed, and the card said
         * <em>"Action rejected."</em> — the one thing that had definitively not happened.
         * The audit row said {@code approved}, so the two halves of the product disagreed
         * about what the user had just done.
         *
         * <p>Operator-facing text, never document content: "the document has no summarisable
         * content", not the content itself.
         */
        String failureReason,

        /**
         * The decision that ACTUALLY STANDS, when this call did not make it. Null when this
         * call is the one that decided the proposal.
         *
         * <p>Added Day 20 for a reported bug: a user approved a create-task proposal, then
         * pressed Reject on the same card, and the card answered "Task created: University
         * admission policy." The server was right — a proposal is decided once, and
         * rejecting afterwards must not delete a task that exists — but the UI reported a
         * creation as though the Reject click had caused it. The click was silently ignored.
         *
         * <p>With this, the client can say what actually happened: your rejection was not
         * applied, because this was already approved.
         */
        ActionDecision replayedDecision
) {
    public static ActionResult completed(String actionId, ActionType type, Object result) {
        return new ActionResult(actionId, ActionStatus.completed, type, result, null, null);
    }

    public static ActionResult rejected(String actionId, ActionType type) {
        return new ActionResult(actionId, ActionStatus.rejected, type, null, null, null);
    }

    public static ActionResult failed(String actionId, ActionType type, String reason) {
        return new ActionResult(actionId, ActionStatus.failed, type, null, reason, null);
    }
}
