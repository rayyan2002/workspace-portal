package com.knowledgeassistant.common;

import org.springframework.http.HttpStatus;

/** A user id that no account matches. 404, like the other not-found cases. */
public class UserNotFoundException extends DomainException {
    public UserNotFoundException(String message) {
        super(message, ErrorCode.NOT_FOUND, HttpStatus.NOT_FOUND);
    }
}
