package com.bluestone.knowledge_assistant.task.dto; // Move to task/dto if it isn't there

import com.bluestone.knowledge_assistant.task.TaskStatus;
import jakarta.validation.constraints.NotNull;

public record TaskStatusUpdateRequest(
        @NotNull(message = "Status cannot be null")
        TaskStatus status
) {}