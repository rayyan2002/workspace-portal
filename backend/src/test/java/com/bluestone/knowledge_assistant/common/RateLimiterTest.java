package com.bluestone.knowledge_assistant.common;

import org.junit.jupiter.api.Test;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Day 17: the rate limiter, tested directly because it is switched OFF everywhere else.
 *
 * <p><strong>Why it is off in the test profile, and why that makes this file necessary.</strong>
 * The suite runs in one JVM and every request arrives from the same mock address, so a
 * production limit of five registrations per hour throttles the twenty-third test rather
 * than any attacker. Wiring it live into the integration tests made five of them fail with
 * 429 — a measurement, not a guess. Disabling it there and asserting it here puts the
 * behaviour under test without making every unrelated test order-dependent.
 *
 * <p>The cost is stated plainly: nothing here proves the limiter is WIRED to the endpoints.
 * That is covered by reading two call sites, and by
 * {@code RateLimitPropertiesValidationTest} proving the configuration binds.
 */
class RateLimiterTest {

    private static final Duration WINDOW = Duration.ofMinutes(1);

    private RateLimiter enabled() {
        return new RateLimiter(new RateLimitProperties(10, 5, 5, 20, true));
    }

    // --- the counting ---------------------------------------------------------

    @Test
    void requestsUpToTheLimitAreAllowed() {
        RateLimiter limiter = enabled();

        for (int i = 0; i < 3; i++) {
            final int attempt = i;
            assertDoesNotThrow(() -> limiter.check("login", "10.0.0.1", 3, WINDOW),
                    "attempt " + attempt + " was within the limit");
        }
    }

    @Test
    void theRequestAfterTheLimitIsRefused() {
        RateLimiter limiter = enabled();
        for (int i = 0; i < 3; i++) {
            limiter.check("login", "10.0.0.1", 3, WINDOW);
        }

        assertThrows(RateLimitedException.class,
                () -> limiter.check("login", "10.0.0.1", 3, WINDOW));
    }

    @Test
    void theRefusalSaysHowLongToWait() {
        // A limit that only says "no" is indistinguishable from a broken endpoint, and a
        // client that cannot tell those apart retries immediately — the exact behaviour the
        // limit exists to stop.
        RateLimiter limiter = enabled();
        limiter.check("login", "10.0.0.1", 1, WINDOW);

        RateLimitedException refused = assertThrows(RateLimitedException.class,
                () -> limiter.check("login", "10.0.0.1", 1, WINDOW));

        assertTrue(refused.getRetryAfterSeconds() >= 1, "Retry-After must be a usable number");
        assertTrue(refused.getRetryAfterSeconds() <= 60, "and no longer than the window");
        assertTrue(refused.getMessage().contains("try again"), refused.getMessage());
        assertEquals(ErrorCode.RATE_LIMITED, refused.getCode());
    }

    // --- the isolation that makes a shared limiter safe -----------------------

    @Test
    void oneCallerRunningOutDoesNotAffectAnother() {
        // THE PROPERTY THAT MATTERS MOST. If the key were ignored or collided, one
        // aggressive address would lock out every other user — a denial of service delivered
        // by the thing meant to prevent one.
        RateLimiter limiter = enabled();
        for (int i = 0; i < 3; i++) {
            limiter.check("login", "10.0.0.1", 3, WINDOW);
        }

        assertThrows(RateLimitedException.class,
                () -> limiter.check("login", "10.0.0.1", 3, WINDOW));
        assertDoesNotThrow(() -> limiter.check("login", "10.0.0.2", 3, WINDOW),
                "a different caller must have its own allowance");
    }

    @Test
    void eachBucketHasItsOwnAllowance() {
        // Exhausting uploads must not lock a user out of logging in.
        RateLimiter limiter = enabled();
        limiter.check("upload", "user-1", 1, WINDOW);
        assertThrows(RateLimitedException.class, () -> limiter.check("upload", "user-1", 1, WINDOW));

        assertDoesNotThrow(() -> limiter.check("login", "user-1", 1, WINDOW));
    }

    @Test
    void theWindowExpiresAndTheAllowanceReturns() {
        // A zero-length window expires immediately, which is how this is tested without a
        // sleep: a test that waits a minute is a test nobody runs.
        RateLimiter limiter = enabled();
        Duration instant = Duration.ofNanos(1);

        limiter.check("login", "10.0.0.1", 1, instant);
        assertDoesNotThrow(() -> limiter.check("login", "10.0.0.1", 1, instant),
                "the previous window had expired, so the counter should have restarted");
    }

    // --- the switch -----------------------------------------------------------

    @Test
    void aDisabledLimiterNeverRefusesAnything() {
        RateLimiter limiter = new RateLimiter(new RateLimitProperties(10, 5, 5, 20, false));

        for (int i = 0; i < 100; i++) {
            limiter.check("login", "10.0.0.1", 1, WINDOW);
        }

        assertEquals(0, limiter.trackedKeys(),
                "a disabled limiter must not accumulate state either");
    }

    @Test
    void aDisabledLimiterCostsNoMemory() {
        // Not merely "allows everything" — it must also not grow a map that nothing reads.
        RateLimiter limiter = new RateLimiter(new RateLimitProperties(10, 5, 5, 20, false));

        for (int i = 0; i < 1000; i++) {
            limiter.check("login", "10.0.0." + i, 1, WINDOW);
        }

        assertEquals(0, limiter.trackedKeys());
    }

    // --- bookkeeping ----------------------------------------------------------

    @Test
    void anExpiredWindowIsReplacedRatherThanAccumulated() {
        // The lazy sweep: a key touched after its window expired starts a fresh window in
        // the same slot. Without it the map would grow by one entry per caller forever.
        RateLimiter limiter = enabled();
        Duration instant = Duration.ofNanos(1);

        for (int i = 0; i < 50; i++) {
            limiter.check("login", "10.0.0.1", 1, instant);
        }

        assertEquals(1, limiter.trackedKeys(), "one caller must occupy one slot");
    }

    @Test
    void distinctCallersEachOccupyOneSlot() {
        RateLimiter limiter = enabled();

        for (int i = 0; i < 25; i++) {
            limiter.check("login", "10.0.0." + i, 10, WINDOW);
        }

        assertEquals(25, limiter.trackedKeys());
    }
}
