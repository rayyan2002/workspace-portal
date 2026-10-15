package com.knowledgeassistant.task.dto; // Move to task/dto if it isn't there

import com.knowledgeassistant.task.TaskStatus;
import jakarta.validation.constraints.NotNull;

public record TaskStatusUpdateRequest(
        @NotNull(message = "Status cannot be null")
        TaskStatus status
) {}