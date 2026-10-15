package com.knowledgeassistant.config;

import com.knowledgeassistant.common.ApiError;
import com.knowledgeassistant.common.DomainException;
import com.knowledgeassistant.common.ErrorCode;
import com.knowledgeassistant.common.RateLimitedException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

import java.time.Instant;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    // 1. The Consolidated Domain Exception Handler
    // This entirely replaces specific handlers for ChatNotFound, Unauthorized, DocumentValidation, etc.
    /**
     * 429, with {@code Retry-After}. Day 17.
     *
     * <p>Handled before the generic {@link DomainException} branch because the HEADER is the
     * point. The status alone tells a client it was refused; {@code Retry-After} tells it
     * when to come back, and it is the difference between a well-behaved client backing off
     * and one hammering the endpoint the limit exists to protect. Browsers, fetch wrappers
     * and load balancers all understand it.
     */
    @ExceptionHandler(RateLimitedException.class)
    public ResponseEntity<ApiError> handleRateLimited(RateLimitedException ex) {
        ApiError apiError = new ApiError(ex.getMessage(), ex.getCode(), Instant.now(), MDC.get("traceId"));
        return ResponseEntity.status(ex.getStatus())
                .header("Retry-After", String.valueOf(ex.getRetryAfterSeconds()))
                .body(apiError);
    }

    @ExceptionHandler(DomainException.class)
    public ResponseEntity<ApiError> handleDomainException(DomainException ex) {
        log.warn("Domain exception thrown: {} (Code: {})", ex.getMessage(), ex.getCode());
        ApiError apiError = new ApiError(ex.getMessage(), ex.getCode(), Instant.now(), MDC.get("traceId"));
        return ResponseEntity.status(ex.getStatus()).body(apiError);
    }

    // 2. Framework Leak: Unmapped URLs (Prevents generic 500s on typos)
    @ExceptionHandler(org.springframework.web.servlet.resource.NoResourceFoundException.class)
    public ResponseEntity<ApiError> handleNoResourceFound(org.springframework.web.servlet.resource.NoResourceFoundException ex) {
        log.warn("Resource not found: {}", ex.getResourcePath());
        // FIX: Replaced ErrorCode.BAD_REQUEST with ErrorCode.NOT_FOUND
        ApiError apiError = new ApiError("Endpoint not found: " + ex.getResourcePath(), ErrorCode.NOT_FOUND, Instant.now(), MDC.get("traceId"));
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(apiError);
    }

    @ExceptionHandler(org.springframework.web.HttpRequestMethodNotSupportedException.class)
    public ResponseEntity<ApiError> handleMethodNotSupported(org.springframework.web.HttpRequestMethodNotSupportedException ex) {
        log.warn("Method not supported: {}", ex.getMethod());
        // FIX: Replaced ErrorCode.BAD_REQUEST with ErrorCode.METHOD_NOT_ALLOWED
        ApiError apiError = new ApiError("HTTP Method not supported: " + ex.getMethod(), ErrorCode.METHOD_NOT_ALLOWED, Instant.now(), MDC.get("traceId"));
        return ResponseEntity.status(HttpStatus.METHOD_NOT_ALLOWED).body(apiError);
    }

    // 4. Framework: Validation Errors (@Valid body payloads)
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> handleValidationErrors(MethodArgumentNotValidException ex) {
        String errorMessage = ex.getBindingResult().getFieldErrors().stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .findFirst()
                .orElse("Validation failed");

        log.warn("Validation error: {}", errorMessage);
        ApiError apiError = new ApiError(errorMessage, ErrorCode.VALIDATION_ERROR, Instant.now(), MDC.get("traceId"));
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(apiError);
    }

    // 5. Framework: Malformed JSON Requests
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> handleHttpMessageNotReadable(HttpMessageNotReadableException ex) {
        log.warn("Malformed JSON request received", ex);
        ApiError apiError = new ApiError("Malformed JSON request structure.", ErrorCode.BAD_REQUEST, Instant.now(), MDC.get("traceId"));
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(apiError);
    }

    // 6. Framework: Path Variable / Query Param Type Mismatch (e.g. bad UUID)
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> handleTypeMismatch(MethodArgumentTypeMismatchException ex) {
        String message = String.format("Invalid value '%s' for parameter '%s'.", ex.getValue(), ex.getName());
        log.warn("Type mismatch error: {}", message);
        ApiError apiError = new ApiError(message, ErrorCode.BAD_REQUEST, Instant.now(), MDC.get("traceId"));
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(apiError);
    }

    // 7. Framework: File Upload Size Exceeded
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ApiError> handleMaxSizeException(MaxUploadSizeExceededException ex) {
        log.warn("Max upload size exceeded", ex);
        ApiError apiError = new ApiError("File exceeds maximum allowed size.", ErrorCode.FILE_TOO_LARGE, Instant.now(), MDC.get("traceId"));
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE).body(apiError);
    }

    // 8. The Catch-All 500
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> handleAllExceptions(Exception ex) {
        log.error("Unhandled internal server error caught by global handler", ex);
        ApiError apiError = new ApiError("An unexpected internal server error occurred.", ErrorCode.INTERNAL_ERROR, Instant.now(), MDC.get("traceId"));
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(apiError);
    }
}