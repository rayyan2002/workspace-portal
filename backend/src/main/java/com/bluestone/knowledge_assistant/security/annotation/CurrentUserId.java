package com.bluestone.knowledge_assistant.security.annotation;

import org.springframework.security.core.annotation.AuthenticationPrincipal;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Injects the authenticated user's id into a controller parameter.
 *
 * <p>A meta-annotation over {@code @AuthenticationPrincipal(expression = "id")}, resolved
 * by Spring Security's own {@code AuthenticationPrincipalArgumentResolver}. Keeps call
 * sites reading {@code @CurrentUserId UUID userId} rather than
 * {@code @AuthenticationPrincipal UserPrincipal principal} followed by {@code getId()},
 * without any custom resolver of our own.
 */
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@AuthenticationPrincipal(expression = "id")
public @interface CurrentUserId {
}
