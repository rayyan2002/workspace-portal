package com.knowledgeassistant.common;

import org.springframework.http.HttpStatus;

public class TaskNotFoundException extends DomainException {
    public TaskNotFoundException(String message) {
        // Swapped! message comes first, then ErrorCode, then HttpStatus
        super(message, ErrorCode.TASK_NOT_FOUND, HttpStatus.NOT_FOUND);
    }
}