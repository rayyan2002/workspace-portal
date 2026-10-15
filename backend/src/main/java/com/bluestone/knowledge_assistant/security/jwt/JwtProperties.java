package com.bluestone.knowledge_assistant.security.jwt;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

/**
 * JWT settings, bound from the {@code app.jwt.*} namespace.
 *
 * @param secret            HMAC-SHA signing key. Must be at least 256 bits (32 bytes) for
 *                          HS256; JJWT refuses a weaker key rather than silently degrading.
 *                          Supplied by the environment in any real deployment.
 * @param issuer            value of the {@code iss} claim, validated on every parse
 * @param accessTokenTtl    how long an access token stays valid. Short by design: an access
 *                          token cannot be revoked, so its blast radius is its lifetime.
 * @param refreshTokenTtl   how long a refresh token stays valid. Long, but revocable,
 *                          because it lives in the database.
 */
@ConfigurationProperties(prefix = "app.jwt")
public record JwtProperties(
        String secret,
        String issuer,
        Duration accessTokenTtl,
        Duration refreshTokenTtl
) {}
