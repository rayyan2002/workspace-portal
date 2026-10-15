package com.knowledgeassistant.security;

import com.knowledgeassistant.common.ApiError;
import com.knowledgeassistant.common.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.time.Instant;

/**
 * Answers 401 when an unauthenticated request reaches a protected endpoint.
 *
 * <p>Written by hand for the same reason the Day-16 filter was: Spring Security's entry
 * point runs inside its own filter chain, upstream of the DispatcherServlet, so
 * {@code @RestControllerAdvice} never sees it. Without this, the default is an empty body
 * with a {@code WWW-Authenticate} header — the one response shape in the API that would
 * not match {@link ApiError}.
 */
@Component
public class RestAuthenticationEntryPoint implements AuthenticationEntryPoint {

    private static final Logger log = LoggerFactory.getLogger(RestAuthenticationEntryPoint.class);

    private final ObjectMapper objectMapper;

    public RestAuthenticationEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void commence(HttpServletRequest request, HttpServletResponse response,
                         AuthenticationException authException) throws IOException {

        log.warn("Unauthenticated request to {} {}: {}",
                request.getMethod(), request.getRequestURI(), authException.getMessage());

        ApiError body = new ApiError(
                "Authentication required. Provide a valid bearer token.",
                ErrorCode.UNAUTHORIZED,
                Instant.now(),
                MDC.get("traceId"));

        response.setStatus(HttpStatus.UNAUTHORIZED.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding("UTF-8");
        objectMapper.writeValue(response.getWriter(), body);
    }
}
