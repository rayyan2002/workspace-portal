package com.knowledgeassistant.action.dto;
import com.knowledgeassistant.task.TaskPriority;
import java.util.UUID;

public record SummarizePayload(
        UUID documentId,
        String documentName
) implements ActionPayload {}

