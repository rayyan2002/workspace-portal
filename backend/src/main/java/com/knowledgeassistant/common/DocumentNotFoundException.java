package com.knowledgeassistant.common;

import org.springframework.http.HttpStatus;

public class DocumentNotFoundException extends DomainException {
    public DocumentNotFoundException(String message) {
        super(message, ErrorCode.DOCUMENT_NOT_FOUND, HttpStatus.NOT_FOUND);
    }
}