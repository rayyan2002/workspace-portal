package com.knowledgeassistant.task.dto;

import com.knowledgeassistant.task.Task;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.UUID;

public record TaskDto(
        UUID id,
        String title,
        String priority,
        String status,
        String createdAt,
        String completedAt,
        @JsonProperty("sourceSessionId") UUID sessionId,

        /**
         * The message whose reply proposed this task — V23. Null for tasks created before
         * proposals were persisted, which link to the session and no closer.
         */
        UUID sourceMessageId
) {
    public static TaskDto from(Task task) {
        return from(task, null);
    }

    public static TaskDto from(Task task, UUID sourceMessageId) {
        return new TaskDto(
                task.getId(),
                task.getTitle(),
                task.getPriority() != null ? task.getPriority().name().replace('_', '-') : null,
                task.getStatus() != null ? task.getStatus().name().replace('_', '-') : null,
                task.getCreatedAt() != null ? task.getCreatedAt().toString() : null,
                task.getCompletedAt() != null ? task.getCompletedAt().toString() : null,
                task.getSessionId(),
                sourceMessageId
        );
    }
}