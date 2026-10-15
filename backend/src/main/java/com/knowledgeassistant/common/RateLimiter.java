package com.knowledgeassistant.common;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * A fixed-window request counter, in memory. Day 17.
 *
 * <p><strong>WHAT THIS IS NOT.</strong> It is not a distributed rate limiter. The counters
 * live in one JVM's heap, so two instances behind a load balancer would each allow the full
 * quota, and a restart forgets everything. That is a real limitation and it is the right
 * trade here: this application runs as a single process, and the alternative — Redis, or
 * Bucket4j with a backing store — is infrastructure bought for a problem nobody has yet.
 * When a second instance appears, this class is where that decision gets revisited.
 *
 * <p><strong>Fixed window rather than a token bucket</strong>, also deliberately. A fixed
 * window allows a burst of up to 2x the limit across a window boundary, which a bucket does
 * not. For brute-force protection that is irrelevant — the attacker still cannot exceed the
 * average rate — and a fixed window is about fifteen lines, auditable at a glance, with no
 * clock arithmetic to get subtly wrong. A limiter nobody can read is a limiter nobody
 * trusts.
 *
 * <p><strong>Keys are caller-supplied and never raw user input.</strong> Callers pass an IP
 * address or a user id. Keying on something an attacker controls freely — an email address,
 * say — lets them sidestep the limit by varying it, and lets them grow this map without
 * bound.
 *
 * <p>The map is swept lazily: a key is only removed when it is next touched after its window
 * expired, so an idle key costs one entry until something else triggers a sweep. Bounded by
 * {@link #MAX_TRACKED_KEYS} so a spray of distinct IPs cannot exhaust memory — the exact
 * attack a rate limiter is supposed to blunt rather than enable.
 */
@Component
public class RateLimiter {

    private static final Logger log = LoggerFactory.getLogger(RateLimiter.class);

    /**
     * Beyond this many distinct keys the limiter stops admitting NEW ones and logs.
     *
     * <p>FAILS CLOSED for new keys and open for existing ones. The alternative — evicting
     * oldest — is what an attacker wants: spray enough addresses and the entry tracking
     * their brute force gets evicted. Refusing new keys degrades availability for new
     * callers under attack, which is the lesser harm and is visible in the log.
     */
    private static final int MAX_TRACKED_KEYS = 100_000;

    private final Map<String, Window> windows = new ConcurrentHashMap<>();
    private final boolean enabled;

    public RateLimiter(RateLimitProperties properties) {
        this.enabled = properties.enabled();
        if (!enabled) {
            // Logged at WARN, not INFO. A disabled rate limiter is a deliberate choice in a
            // test profile and a serious one anywhere else, and it should be visible in the
            // first lines of a startup log rather than discovered during an incident.
            log.warn("rate limiting is DISABLED (app.security.rate-limit.enabled=false)");
        }
    }

    /** One caller's counter for one window. */
    private record Window(Instant expiresAt, AtomicInteger count) {
    }

    /**
     * Records one request and reports whether it is allowed.
     *
     * @param bucket   what is being limited — "login", "upload". Part of the key, so the
     *                 same caller gets an independent allowance for each.
     * @param key      the caller: an IP address or a user id. Never raw user input.
     * @param limit    requests permitted per window
     * @param window   the window length
     * @throws RateLimitedException when the caller is over the limit
     */
    public void check(String bucket, String key, int limit, Duration window) {
        if (!enabled) {
            return;
        }
        Instant now = Instant.now();
        String composite = bucket + ":" + key;

        Window current = windows.compute(composite, (ignored, existing) -> {
            if (existing == null || now.isAfter(existing.expiresAt())) {
                // Expired or never seen: start a fresh window. This is also the lazy sweep —
                // a stale entry is replaced rather than accumulated.
                return new Window(now.plus(window), new AtomicInteger(1));
            }
            existing.count().incrementAndGet();
            return existing;
        });

        if (windows.size() > MAX_TRACKED_KEYS) {
            // Logged at ERROR because it means either an attack or a key chosen badly enough
            // to be unbounded, and both need a human.
            log.error("rate_limiter.capacity tracked={} — refusing new keys", windows.size());
        }

        int used = current.count().get();
        if (used > limit) {
            long retryAfter = Math.max(1, Duration.between(now, current.expiresAt()).toSeconds());
            // The KEY is not logged. For login it is an IP address, which is personal data,
            // and LogRedactionTest exists to keep that kind of thing out of the log.
            log.warn("rate_limited bucket={} used={} limit={} retryAfterSeconds={}",
                    bucket, used, limit, retryAfter);
            throw new RateLimitedException(
                    "Too many requests. Please try again in " + retryAfter + " seconds.",
                    retryAfter);
        }
    }

    /** Visible for tests: forget everything. */
    public void reset() {
        windows.clear();
    }

    /** Visible for tests: how many keys are currently tracked. */
    public int trackedKeys() {
        return windows.size();
    }
}
