package com.knowledgeassistant.genai;

import com.knowledgeassistant.common.DomainException;
import com.knowledgeassistant.common.ErrorCode;
import org.springframework.http.HttpStatus;

/**
 * The AI service could not answer, and it is not the user's fault.
 *
 * <p>Three causes, one status. All three are "try again shortly" rather than "you did
 * something wrong", so each maps to {@code 503} with a message a person can act on, never a
 * stack trace — per INTEGRATION_CONTRACT.md's failure table.
 *
 * <p>They differ in one respect that matters: <strong>whether retrying is free.</strong>
 * Connection-refused and models-loading fail in microseconds and can resolve on their own.
 * A timeout has already cost the user ninety seconds and may still be generating on the
 * other side, so retrying it turns one slow request into a three-minute one. That
 * distinction lives here rather than in the client, so it cannot be re-decided by whoever
 * writes the next caller.
 */
public class GenAiUnavailableException extends DomainException {

    private final boolean worthRetrying;

    private GenAiUnavailableException(String message, boolean worthRetrying) {
        super(message, ErrorCode.AI_UNAVAILABLE, HttpStatus.SERVICE_UNAVAILABLE);
        this.worthRetrying = worthRetrying;
    }

    /** Connection refused — the service is not running at all. Cheap to have tried. */
    public static GenAiUnavailableException unreachable() {
        return new GenAiUnavailableException(
                "The AI service is unavailable. Please try again shortly.", true);
    }

    /** 503 MODEL_NOT_READY — the process is up, the models are still loading. */
    public static GenAiUnavailableException modelsLoading() {
        return new GenAiUnavailableException(
                "The AI service is still starting up. Please try again in a moment.", true);
    }

    /**
     * A reason the GenAI service gave for itself.
     *
     * <p>Added on Day 13, when a cloud model running out of daily quota started producing
     * the same 503 as a local model still loading at boot. Substituting "still starting up"
     * for both told a user to wait for something that would never change — the free-tier cap
     * is per day and per model, so waiting is the one thing that cannot help.
     *
     * <p>Not worth retrying: whatever the upstream said, it already tried.
     */
    public static GenAiUnavailableException because(String reason) {
        return new GenAiUnavailableException(
                reason == null || reason.isBlank()
                        ? "The AI service is unavailable. Please try again shortly."
                        : reason,
                false);
    }

    /** Exceeded the configured timeout. NOT worth retrying: see the class note. */
    public static GenAiUnavailableException timedOut(long seconds) {
        return new GenAiUnavailableException(
                "The AI took longer than " + seconds + " seconds to answer. Please try again.", false);
    }

    public boolean isWorthRetrying() {
        return worthRetrying;
    }
}
