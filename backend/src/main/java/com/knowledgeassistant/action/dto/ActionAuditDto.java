package com.knowledgeassistant.action.dto;

import com.knowledgeassistant.action.ActionAudit;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.UUID;

public record ActionAuditDto(
        UUID id,
        String actionId,
        UUID sessionId,
        String type,
        String decision,
        @JsonProperty("timestamp") String timestamp,

        /**
         * What execution did, as opposed to what the user decided — V21/V22.
         *
         * <p>Exposed because the audit trail is now where an approved slow action LIVES
         * while it runs: the decision is acknowledged instantly and the work finishes in
         * the background, so without this the row would say "approved" and nothing more
         * for two minutes.
         *
         * <p>Null for rows decided before V21.
         */
        String status,

        /** The stored result, replayed verbatim. Null unless status is completed. */
        Object result,

        /** Operator-facing text. Null unless status is failed. */
        String failureReason,

        /**
         * The message whose reply carried this proposal — V23.
         *
         * <p>Lets the audit trail link to the exact prompt rather than to the conversation.
         * Null for actions decided before proposals were persisted, which keep linking to
         * the session and no closer.
         */
        UUID messageId
) {
    public static ActionAuditDto from(ActionAudit audit) {
        return from(audit, null, null);
    }

    /**
     * @param result the parsed stored result, or null. Passed in rather than parsed here so
     *               this DTO keeps no opinion about JSON — the service owns the mapper.
     */
    public static ActionAuditDto from(ActionAudit audit, Object result) {
        return from(audit, result, null);
    }

    public static ActionAuditDto from(ActionAudit audit, Object result, UUID messageId) {
        return new ActionAuditDto(
                audit.getId(),
                audit.getActionId(),
                audit.getSessionId(),
                audit.getType().name(),
                audit.getDecision().name(),
                audit.getCreatedAt() != null ? audit.getCreatedAt().toString() : null,
                audit.getStatus() != null ? audit.getStatus().name() : null,
                result,
                audit.getFailureReason(),
                messageId
        );
    }
}