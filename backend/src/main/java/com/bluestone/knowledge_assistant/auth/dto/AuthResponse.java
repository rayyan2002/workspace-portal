package com.bluestone.knowledge_assistant.auth.dto;

import java.util.List;

/**
 * The token pair returned by login and refresh.
 *
 * @param expiresIn access-token lifetime in SECONDS, so the client can refresh proactively
 *                  instead of waiting to be surprised by a 401
 */
public record AuthResponse(
        String accessToken,
        String refreshToken,
        String tokenType,
        long expiresIn,
        UserDto user,
        List<String> roles
) {
    private static final String BEARER = "Bearer";

    public static AuthResponse of(String accessToken, String refreshToken, long expiresIn,
                                  UserDto user, List<String> roles) {
        return new AuthResponse(accessToken, refreshToken, BEARER, expiresIn, user, roles);
    }
}
