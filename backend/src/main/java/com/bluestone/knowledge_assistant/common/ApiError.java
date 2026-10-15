package com.bluestone.knowledge_assistant.common;

import java.time.Instant;

public record ApiError(
        String message,
        ErrorCode code,
        Instant timestamp,
        String traceId
) {}