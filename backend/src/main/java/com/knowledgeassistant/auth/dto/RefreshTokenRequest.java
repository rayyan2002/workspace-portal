package com.knowledgeassistant.auth.dto;

import jakarta.validation.constraints.NotBlank;

public record RefreshTokenRequest(
        @NotBlank(message = "Refresh token is required")
        String refreshToken
) {

    /** The refresh token is a live credential with a seven-day life. */
    @Override
    public String toString() {
        return "RefreshTokenRequest[refreshToken=***]";
    }
}
