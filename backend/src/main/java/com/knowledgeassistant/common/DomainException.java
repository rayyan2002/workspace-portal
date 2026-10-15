package com.knowledgeassistant.common;

import org.springframework.http.HttpStatus;

public abstract class DomainException extends RuntimeException {
    private final ErrorCode code;
    private final HttpStatus status;

    protected DomainException(String message, ErrorCode code, HttpStatus status) {
        super(message);
        this.code = code;
        this.status = status;
    }

    public ErrorCode getCode() { return code; }
    public HttpStatus getStatus() { return status; }
}