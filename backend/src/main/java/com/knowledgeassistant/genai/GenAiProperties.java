package com.knowledgeassistant.genai;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;

/**
 * Settings for the GenAI service, bound from {@code app.genai.*}.
 *
 * @param baseUrl        where the Python service listens. It binds 127.0.0.1 deliberately —
 *                       it has no authentication and trusts the {@code allowed_document_ids}
 *                       it is handed, so anyone who can reach it can read any document.
 * @param timeout        how long to wait for an answer. <strong>150 seconds, and every
 *                       revision of it has been a measurement.</strong> Day 1 set 45s from an
 *                       extrapolated estimate and deferred the real decision; Day 7 measured
 *                       30.8s mean and 57.7s worst, so Day 8 set 90s. Day 13 raised the
 *                       generation cap from 200 to 500 tokens, and decode runs at 4-8 tokens/s:
 *                       500 tokens is up to 125s of decode plus ~10s of prefill, so a slow
 *                       local answer would FAIL at 90s where it previously arrived truncated.
 *                       The cap change quietly converted "incomplete answer" into "no answer".
 *                       <p>Only the local backend is exposed to this — Gemini decodes in
 *                       seconds. And 150s is no more comfortable than 90s was: a
 *                       two-and-a-half-minute synchronous request is the strongest argument
 *                       for the asynchronous answer path, which is why it sits on Day 16.
 * @param connectTimeout establishing a TCP connection to a loopback address either works
 *                       immediately or the service is down. Seconds here, not minutes:
 *                       a slow connect is a dead service, not a slow answer.
 * @param topK           chunks to retrieve. Sent explicitly, so this value wins over
 *                       the Python default rather than agreeing with it.
 * @param historyTurns   how many earlier messages to send. The service uses history only as a
 *                       FALLBACK — when a question matches nothing on its own — so this is not
 *                       paid on every request, but it is paid on every prompt, because the
 *                       user's earlier questions are rendered into it.
 * @param minScore       cosine similarity floor. Python's default is 0.60, measured on Day 6.
 *                       Sent explicitly so a change on either side is visible in one diff
 *                       rather than silently inherited.
 */
/**
 * <p><strong>VALIDATED SINCE DAY 17, and the measurement is why.</strong> Eight deliberately
 * bad values were put through this record and <em>all eight were accepted</em> — {@code
 * top-k=0}, {@code min-score=5.0}, {@code timeout=0s}, {@code base-url=not-a-url}. None of
 * them fails here, and that is the problem: they fail LATER, on the far side of a network
 * call, where the error belongs to somebody else.
 *
 * <p>{@code top-k=0} and {@code min-score=5.0} are the clearest case. Python validates both
 * ({@code ge=1}, {@code -1.0 <= x <= 1.0}) and returns 422, so every question a user asks
 * comes back "the AI service refused the request" — a true statement that points at the
 * wrong service. Spring sent the invalid value; Python merely noticed.
 *
 * <p>{@code @Validated} makes these bind-time failures, so the application refuses to start
 * and names the property. One misconfigured deployment that will not boot beats a running
 * one that answers nothing.
 */
@Validated
@ConfigurationProperties(prefix = "app.genai")
public record GenAiProperties(
        @NotBlank(message = "app.genai.base-url must be set (env GENAI_BASE_URL)")
        @Pattern(regexp = "^https?://.+",
                 message = "app.genai.base-url must start with http:// or https:// "
                         + "(env GENAI_BASE_URL)")
        String baseUrl,

        @NotNull(message = "app.genai.timeout must be set, e.g. 150s")
        Duration timeout,

        @NotNull(message = "app.genai.connect-timeout must be set, e.g. 2s")
        Duration connectTimeout,

        // The upper bound is the one the published contract advertises: RetrievalRequest
        // declares top_k with le=50, so anything above it is a guaranteed 422.
        @Min(value = 1, message = "app.genai.top-k must be at least 1 — 0 asks the service "
                + "for no chunks and is rejected there as a 422 on every question")
        int topK,

        @Min(value = 0, message = "app.genai.history-turns cannot be negative")
        int historyTurns,

        // Cosine similarity, so the range is fixed by arithmetic rather than by preference.
        // A floor above 1.0 can never be cleared by anything.
        @DecimalMin(value = "-1.0", message = "app.genai.min-score is a cosine similarity "
                + "and cannot be below -1.0")
        @DecimalMax(value = "1.0", message = "app.genai.min-score is a cosine similarity and "
                + "cannot exceed 1.0 — nothing could ever clear the floor")
        double minScore
) {
    /**
     * Durations are checked here rather than by an annotation: {@code @NotNull} is satisfied
     * by {@code 0s}, and Jakarta Validation has no duration minimum. A zero read timeout
     * makes every request to the GenAI service fail the instant it is sent — which looks
     * exactly like the service being down.
     */
    public GenAiProperties {
        if (timeout != null && timeout.isZero() || timeout != null && timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.genai.timeout must be positive — 0s times out every request "
                            + "immediately, which is indistinguishable from the service being down");
        }
        if (connectTimeout != null && (connectTimeout.isZero() || connectTimeout.isNegative())) {
            throw new IllegalArgumentException("app.genai.connect-timeout must be positive");
        }
    }
}
