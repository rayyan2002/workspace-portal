package com.knowledgeassistant.common;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Day 17: proof that the limiter is actually CONNECTED to the endpoints.
 *
 * <p>{@link RateLimiterTest} proves the counting is right, and proves nothing about whether
 * anything calls it. A limiter that works perfectly and is wired to no endpoint is the
 * comfortable kind of wrong: a class, a test, a green suite, and an unprotected login.
 *
 * <p><strong>Rate limiting is re-enabled for this class alone</strong>, with a limit of 2 so
 * the third request is refused. The rest of the suite keeps it off, because the suite shares
 * one JVM and one mock address — wiring it live everywhere made five unrelated tests fail
 * with 429, which is a measurement of the test environment rather than of the product.
 *
 * <p>Login is used because it is the endpoint that matters: before Day 17 password guessing
 * was bounded only by how fast a machine could send requests. The credentials are deliberately
 * WRONG — a rate limit must apply to failed attempts, which is the entire point of having one.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "app.security.rate-limit.enabled=true",
        "app.security.rate-limit.login-per-minute=2",
})
class RateLimitWiringTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private RateLimiter rateLimiter;

    private static final String BAD_LOGIN = """
            {"email":"nobody@example.com","password":"wrong-password"}""";

    @BeforeEach
    void clearCounters() {
        // The limiter is a singleton shared across this class's tests, and its window is a
        // minute. Without this, the second test inherits the first one's exhausted counter
        // and passes for the wrong reason.
        rateLimiter.reset();
    }

    @Test
    void repeatedFailedLoginsAreEventuallyRefused() throws Exception {
        for (int attempt = 1; attempt <= 2; attempt++) {
            mockMvc.perform(post("/api/auth/login")
                            .contentType(MediaType.APPLICATION_JSON).content(BAD_LOGIN))
                    // 401, not 429: a wrong password within the allowance is an ordinary
                    // failure. Asserting this distinguishes "the limiter fired" from "the
                    // endpoint was broken all along".
                    .andExpect(status().isUnauthorized());
        }

        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON).content(BAD_LOGIN))
                .andExpect(status().isTooManyRequests())
                .andExpect(jsonPath("$.code").value("RATE_LIMITED"));
    }

    @Test
    void theRefusalCarriesRetryAfter() throws Exception {
        // The header is the point. The status says refused; Retry-After says when to come
        // back, and it is the difference between a client backing off and one hammering the
        // endpoint the limit exists to protect.
        for (int attempt = 1; attempt <= 2; attempt++) {
            mockMvc.perform(post("/api/auth/login")
                    .contentType(MediaType.APPLICATION_JSON).content(BAD_LOGIN));
        }

        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON).content(BAD_LOGIN))
                .andExpect(status().isTooManyRequests())
                .andExpect(header().exists("Retry-After"));
    }

    @Test
    void theRefusalDoesNotLeakWhetherTheAccountExists() throws Exception {
        // A 429 that differed between a real and an unknown address would turn the rate
        // limiter into the account-enumeration oracle that /api/auth/forgot-password was
        // deliberately built to avoid being.
        for (int attempt = 1; attempt <= 3; attempt++) {
            mockMvc.perform(post("/api/auth/login")
                    .contentType(MediaType.APPLICATION_JSON).content(BAD_LOGIN));
        }

        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":"someone-else@example.com","password":"wrong"}"""))
                .andExpect(status().isTooManyRequests())
                .andExpect(jsonPath("$.message").value(
                        org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("@"))));
    }
}
