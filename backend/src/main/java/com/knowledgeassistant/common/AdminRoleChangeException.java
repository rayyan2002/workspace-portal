package com.knowledgeassistant.common;

import org.springframework.http.HttpStatus;

/**
 * A role change that would lock everybody out.
 *
 * <p>400 rather than 403: the caller IS allowed to change roles, and the request is
 * well-formed. What is wrong is the outcome — removing the last way back in.
 */
public class AdminRoleChangeException extends DomainException {
    public AdminRoleChangeException(String message) {
        super(message, ErrorCode.BAD_REQUEST, HttpStatus.BAD_REQUEST);
    }
}
