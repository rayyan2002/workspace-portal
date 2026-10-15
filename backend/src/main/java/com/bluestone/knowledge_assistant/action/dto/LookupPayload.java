package com.bluestone.knowledge_assistant.action.dto;
import com.bluestone.knowledge_assistant.task.TaskPriority;
import java.util.UUID;

public record LookupPayload(
        String query
) implements ActionPayload {}
