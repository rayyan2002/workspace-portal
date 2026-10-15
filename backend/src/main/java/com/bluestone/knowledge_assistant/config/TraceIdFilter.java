package com.bluestone.knowledge_assistant.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

@Component
// Must run ahead of Spring Security's chain (order -100), so that the 401 and 403
// written by the entry point and access-denied handler carry a traceId. HIGHEST_PRECEDENCE
// states that relationship rather than leaving it to chance.
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        try {
            String traceId = UUID.randomUUID().toString();
            MDC.put("traceId", traceId);

            // Expose to the frontend Network tab
            response.setHeader("X-Trace-Id", traceId);

            filterChain.doFilter(request, response);
        } finally {
            MDC.clear(); // CRITICAL: Prevent thread-local leakage
        }
    }
}