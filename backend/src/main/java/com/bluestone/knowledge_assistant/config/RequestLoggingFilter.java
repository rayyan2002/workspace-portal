package com.bluestone.knowledge_assistant.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * One line per request: method, path, status, duration.
 *
 * <p>This replaces Logbook, which was configured at TRACE and logged request and
 * response bodies — so every login wrote the plaintext password, the issued JWT and
 * the refresh token to the console. It was removed rather than turned down, because
 * the difference matters: a configuration setting is a fact about a file, and files
 * drift. This filter <em>never reads the body or the headers</em>, so there is no
 * setting that could make it start. The safety is a property of the code's shape,
 * not of a value someone has to keep correct.
 *
 * <p>The path is logged without the query string for the same reason: a password
 * reset token can legitimately arrive in one.
 *
 * <p>Ordered immediately after {@link TraceIdFilter} and therefore OUTSIDE Spring
 * Security's chain (which runs at −100). That placement is deliberate — a request
 * rejected with 401 or 403 never reaches a filter positioned inside the chain, and a
 * rejected request is precisely the one worth having a log line for.
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
public class RequestLoggingFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(RequestLoggingFilter.class);

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {

        long startedAt = System.nanoTime();
        try {
            filterChain.doFilter(request, response);
        } finally {
            long durationMs = (System.nanoTime() - startedAt) / 1_000_000;
            int status = response.getStatus();

            // key=value throughout, so the switch to JSON output at deployment time is
            // a formatting change rather than a rewrite of every call site.
            String message = "http method={} path={} status={} durationMs={}";

            // Server faults deserve to stand out; a 4xx is usually the client's doing
            // and should not read as an incident.
            if (status >= 500) {
                log.error(message, request.getMethod(), request.getRequestURI(), status, durationMs);
            } else if (status >= 400) {
                log.warn(message, request.getMethod(), request.getRequestURI(), status, durationMs);
            } else {
                log.info(message, request.getMethod(), request.getRequestURI(), status, durationMs);
            }
        }
    }

    /** Static assets and the health probe would otherwise dominate the log. */
    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return path.startsWith("/actuator")
                || path.startsWith("/swagger-ui")
                || path.startsWith("/v3/api-docs");
    }
}
