package com.knowledgeassistant.common;

import org.springframework.http.HttpStatus;

// FIX: Now properly extends DomainException
public class UnauthorizedException extends DomainException {
    public UnauthorizedException(String message) {
        super(message, ErrorCode.UNAUTHORIZED, HttpStatus.UNAUTHORIZED);
    }
}