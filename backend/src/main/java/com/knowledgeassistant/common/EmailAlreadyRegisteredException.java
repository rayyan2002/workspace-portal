package com.knowledgeassistant.common;

import org.springframework.http.HttpStatus;

/**
 * 409 rather than 400: the request is well-formed, it conflicts with existing state.
 *
 * <p>This does disclose that an address is registered — unavoidable for a public
 * sign-up form, since the user has to be told why they cannot proceed. Login and
 * password reset stay silent on account existence, so the disclosure is confined to
 * the one place it cannot be avoided.
 */
public class EmailAlreadyRegisteredException extends DomainException {
    public EmailAlreadyRegisteredException(String message) {
        super(message, ErrorCode.EMAIL_ALREADY_REGISTERED, HttpStatus.CONFLICT);
    }
}
