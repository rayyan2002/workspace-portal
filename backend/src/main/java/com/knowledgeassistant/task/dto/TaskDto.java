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
        @JsonProperty("sourceSessionId") UUID sessionId
) {
    public static TaskDto from(Task task) {
        return new TaskDto(
                task.getId(),
                task.getTitle(),
                task.getPriority() != null ? task.getPriority().name().replace('_', '-') : null,
                task.getStatus() != null ? task.getStatus().name().replace('_', '-') : null,
                task.getCreatedAt() != null ? task.getCreatedAt().toString() : null,
                task.getCompletedAt() != null ? task.getCompletedAt().toString() : null,
                task.getSessionId()
        );
    }
}