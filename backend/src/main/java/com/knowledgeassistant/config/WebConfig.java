package com.knowledgeassistant.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Web MVC customisations.
 *
 * <p>Deliberately near-empty: CORS now lives in {@code SecurityConfig} via
 * {@code http.cors()}, and the current-user argument resolver was replaced by Spring
 * Security's own {@code AuthenticationPrincipalArgumentResolver}, which
 * {@code @CurrentUserId} rides on.
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {
}
