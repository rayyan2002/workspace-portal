package com.bluestone.knowledge_assistant.common;

import org.springframework.http.HttpStatus;

public class ChatNotFoundException extends DomainException {
    public ChatNotFoundException(String message) {
        // Enforces the correct HTTP status and Error Code at the domain level
        super(message, ErrorCode.CHAT_NOT_FOUND, HttpStatus.NOT_FOUND);
    }
}