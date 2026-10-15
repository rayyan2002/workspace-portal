package com.knowledgeassistant.action.dto;

import com.knowledgeassistant.action.ActionDecision;
import com.knowledgeassistant.action.ActionType;
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.UUID;

public record ActionRequest(
        // action_audit.action_id is VARCHAR(255)
        @NotBlank @Size(max = 255) String actionId,
        @NotNull UUID sessionId,
        @NotNull ActionDecision decision,
        @NotNull ActionType type,

        // Added visible = true to prevent Jackson from consuming the type field
        @JsonTypeInfo(
                use = JsonTypeInfo.Id.NAME,
                include = JsonTypeInfo.As.EXTERNAL_PROPERTY,
                property = "type",
                visible = true
        )
        @JsonSubTypes({
                @JsonSubTypes.Type(value = CreateTaskPayload.class, name = "create-task"),
                @JsonSubTypes.Type(value = SummarizePayload.class, name = "summarize-document"),
                @JsonSubTypes.Type(value = LookupPayload.class, name = "lookup-knowledge")
        })
        @NotNull(message = "Payload is required")
        @Valid ActionPayload payload
) {}