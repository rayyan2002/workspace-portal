package com.knowledgeassistant.action.dto;
import com.knowledgeassistant.task.TaskPriority;
import java.util.UUID;

public record LookupPayload(
        String query
) implements ActionPayload {}
