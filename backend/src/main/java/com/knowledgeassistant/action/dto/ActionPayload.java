package com.knowledgeassistant.action.dto;

import com.knowledgeassistant.task.TaskPriority;
import java.util.UUID;

public sealed interface ActionPayload permits
        CreateTaskPayload,
        SummarizePayload,
        LookupPayload {}