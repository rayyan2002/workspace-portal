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
        @JsonProperty("timestamp") String timestamp
) {
    public static ActionAuditDto from(ActionAudit audit) {
        return new ActionAuditDto(
                audit.getId(),
                audit.getActionId(),
                audit.getSessionId(),
                audit.getType().name(),
                audit.getDecision().name(),
                audit.getCreatedAt() != null ? audit.getCreatedAt().toString() : null
        );
    }
}