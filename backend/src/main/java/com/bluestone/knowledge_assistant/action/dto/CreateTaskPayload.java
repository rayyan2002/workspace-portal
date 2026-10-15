package com.bluestone.knowledge_assistant.action.dto;

import com.bluestone.knowledge_assistant.task.TaskPriority;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/**
 * Constraints match the tasks table exactly (title VARCHAR(255) NOT NULL, priority NOT NULL).
 * Without them a null or over-long title reached Postgres and surfaced as a 500 from a
 * constraint violation instead of a 400. ActionRequest already cascades @Valid here, so
 * these take effect the moment they exist.
 */
public record CreateTaskPayload(
        @NotBlank(message = "Task title is required")
        @Size(max = 255, message = "Task title must be at most 255 characters")
        String title,

        @NotNull(message = "Task priority is required")
        TaskPriority priority
) implements ActionPayload {}
