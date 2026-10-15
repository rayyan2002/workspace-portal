package com.bluestone.knowledge_assistant.common;

import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * How much traffic one caller may send, bound from {@code app.security.rate-limit.*}. Day 17.
 *
 * <p><strong>These began as constants in two controllers and moved here within the hour.</strong>
 * The test suite exhausted them: it runs in one JVM, every request arrives from the same mock
 * address, and five registrations per hour is a sensible production limit and a guaranteed
 * suite failure. The fix is not a bigger constant — it is that an operational limit is
 * CONFIGURATION, which is the whole subject of this day. A number compiled into a controller
 * cannot be raised for a load test, lowered during an attack, or relaxed for a test profile
 * without a rebuild.
 *
 * <p><strong>The defaults are honest guesses, not measurements.</strong> There is no
 * production traffic to tune against, and a precise-looking figure would imply otherwise.
 * They are set where a person will never notice them and a script will:
 *
 * <ul>
 *   <li>{@code login} 10/minute — a person who has mistyped their password ten times in sixty
 *       seconds will not get it right on the eleventh. Reduces an online brute force from one
 *       address to roughly 14,400 guesses a day.</li>
 *   <li>{@code register} and {@code passwordReset} 5/hour — both create real side effects
 *       (a row, an outbound email) on an address the caller chooses.</li>
 *   <li>{@code upload} 20/minute — the resource protected is the embedding model, not disk.
 *       Since Day 16 an upload runs extraction, chunking and embedding synchronously on the
 *       same CPU that answers every question.</li>
 * </ul>
 *
 * @param loginPerMinute          failed-or-successful login attempts per IP per minute
 * @param registerPerHour         account creations per IP per hour
 * @param passwordResetPerHour    reset requests per IP per hour
 * @param uploadPerMinute         uploads per USER per minute — upload is authenticated, so
 *                                the user id is both available and the thing worth limiting
 * @param enabled                 master switch. Off in tests, which share one JVM and one
 *                                mock address and would otherwise throttle themselves
 */
@Validated
@ConfigurationProperties(prefix = "app.security.rate-limit")
public record RateLimitProperties(
        @Min(value = 1, message = "app.security.rate-limit.login-per-minute must be at least 1 "
                + "— zero would lock every user out permanently")
        int loginPerMinute,

        @Min(value = 1, message = "app.security.rate-limit.register-per-hour must be at least 1")
        int registerPerHour,

        @Min(value = 1, message = "app.security.rate-limit.password-reset-per-hour must be at least 1")
        int passwordResetPerHour,

        @Min(value = 1, message = "app.security.rate-limit.upload-per-minute must be at least 1")
        int uploadPerMinute,

        boolean enabled
) {
}
