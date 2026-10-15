package com.bluestone.knowledge_assistant.common;

import org.springframework.http.HttpStatus;

/**
 * A rejected upload: no file, too large, unsupported type, or an over-long filename.
 *
 * <p>This extended {@code RuntimeException} rather than {@link DomainException}, so
 * {@code GlobalExceptionHandler} — which maps {@code DomainException} — never saw it and
 * every rejection fell through to the catch-all as a <strong>500</strong>. A user
 * uploading a .exe got "internal server error", and the server logged it as an unhandled
 * fault, when both should have said "unsupported file type" with a 400.
 *
 * <p>Nothing caught it because the integration test only uploads a VALID file and the
 * unit tests assert the exception is thrown without asserting the status it maps to.
 * The request log line showing status=500 next to a deliberate "upload_rejected" warning
 * is what made the contradiction visible.
 */
public class DocumentValidationException extends DomainException {

    public DocumentValidationException(String message, ErrorCode errorCode) {
        super(message, errorCode, HttpStatus.BAD_REQUEST);
    }

    /** Retained so existing callers reading the code keep compiling. */
    public ErrorCode getErrorCode() {
        return getCode();
    }
}
