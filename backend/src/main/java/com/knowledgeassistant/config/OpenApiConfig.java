package com.knowledgeassistant.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Declares the bearer scheme so Swagger UI shows an "Authorize" box.
 *
 * <p>Without this, the Day-12 executable examples all stop working the moment the API
 * closes by default: "Try it out" sends no Authorization header and every protected
 * endpoint answers 401. Log in via {@code POST /api/auth/login}, paste the returned
 * token into Authorize, and the examples work again.
 */
@Configuration
public class OpenApiConfig {

    private static final String SCHEME_NAME = "bearerAuth";

    @Bean
    public OpenAPI knowledgeAssistantOpenApi() {
        return new OpenAPI()
                .info(new Info()
                        .title("Knowledge Assistant API")
                        .version("v1")
                        .description("""
                                All endpoints except /api/auth/login, /api/auth/refresh and /api/health require
                                a bearer JWT. POST /api/auth/login for an access/refresh pair, then paste the
                                ACCESS token into Authorize. Access tokens expire after 15 minutes;
                                POST /api/auth/refresh for a new pair.
                                """))
                .addSecurityItem(new SecurityRequirement().addList(SCHEME_NAME))
                .components(new Components().addSecuritySchemes(SCHEME_NAME,
                        new SecurityScheme()
                                .name(SCHEME_NAME)
                                .type(SecurityScheme.Type.HTTP)
                                .scheme("bearer")
                                .bearerFormat("JWT")
                                .description("Access token from POST /api/auth/login")));
    }
}
