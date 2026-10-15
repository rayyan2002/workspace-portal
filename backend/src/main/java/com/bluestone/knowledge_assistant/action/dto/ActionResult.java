package com.bluestone.knowledge_assistant.action.dto;

import com.bluestone.knowledge_assistant.action.ActionStatus;
import com.bluestone.knowledge_assistant.action.ActionType;

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
        String failureReason
) {
    public static ActionResult completed(String actionId, ActionType type, Object result) {
        return new ActionResult(actionId, ActionStatus.completed, type, result, null);
    }

    public static ActionResult rejected(String actionId, ActionType type) {
        return new ActionResult(actionId, ActionStatus.rejected, type, null, null);
    }

    public static ActionResult failed(String actionId, ActionType type, String reason) {
        return new ActionResult(actionId, ActionStatus.failed, type, null, reason);
    }
}
