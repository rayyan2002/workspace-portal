package com.bluestone.knowledge_assistant.chat.dto;

import java.util.Map;

public record ActionProposalDto(
        String id,
        String type,
        String label,
        Map<String, Object> payload
) {}