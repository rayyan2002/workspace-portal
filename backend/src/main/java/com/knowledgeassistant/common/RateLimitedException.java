package com.knowledgeassistant.common;

import org.springframework.http.HttpStatus;

/**
 * Too many requests from one caller, too quickly. Day 17.
 *
 * <p><strong>429, and the message says how long to wait.</strong> A rate limit that only
 * says "no" is indistinguishable from a broken endpoint, and a user who cannot tell those
 * apart retries immediately — which is the behaviour the limit exists to stop.
 */
public class RateLimitedException extends DomainException {

    private final long retryAfterSeconds;

    public RateLimitedException(String message, long retryAfterSeconds) {
        super(message, ErrorCode.RATE_LIMITED, HttpStatus.TOO_MANY_REQUESTS);
        this.retryAfterSeconds = retryAfterSeconds;
    }

    /** Seconds until the caller may try again. Sent as the {@code Retry-After} header. */
    public long getRetryAfterSeconds() {
        return retryAfterSeconds;
    }
}
