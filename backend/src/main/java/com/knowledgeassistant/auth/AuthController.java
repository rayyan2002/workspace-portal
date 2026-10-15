package com.knowledgeassistant.auth;

import com.knowledgeassistant.auth.dto.AuthResponse;
import com.knowledgeassistant.auth.dto.LoginRequest;
import com.knowledgeassistant.auth.dto.ForgotPasswordRequest;
import com.knowledgeassistant.auth.dto.RefreshTokenRequest;
import com.knowledgeassistant.auth.dto.RegisterRequest;
import com.knowledgeassistant.common.RateLimitProperties;
import com.knowledgeassistant.common.RateLimiter;
import jakarta.servlet.http.HttpServletRequest;

import java.time.Duration;
import com.knowledgeassistant.auth.dto.ResetPasswordRequest;
import com.knowledgeassistant.auth.dto.UserDto;
import com.knowledgeassistant.security.annotation.CurrentUserId;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.security.SecurityRequirements;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/auth")
@Tag(name = "Authentication", description = "Login, token refresh, and logout")
public class AuthController {

    /**
     * Rate limits, Day 17. The numbers are chosen to be invisible to a person and ruinous to
     * a script; there is no production traffic to tune them against, and that is said out
     * loud rather than implied by a precise-looking figure.
     *
     * <p><strong>LOGIN IS THE ONE THAT MATTERS.</strong> Before this, password guessing was
     * bounded only by how fast a machine could send requests. 10 attempts a minute is more
     * than any human needs — a person who has mistyped their password ten times in sixty
     * seconds is not going to get it right on the eleventh — and it reduces an online
     * brute force to roughly 14,400 guesses a day from one address.
     *
     * <p>Keyed by IP, because login has no authenticated user yet. That means a shared NAT
     * can exhaust another user's allowance, which is a real cost of the only key available.
     * Keying on the submitted email instead would be worse: an attacker varies it freely,
     * sidesteps the limit entirely, and grows the map without bound.
     */
    private final RateLimiter rateLimiter;
    private final RateLimitProperties rateLimits;

    /**
     * Whether {@code X-Forwarded-For} may be believed. FALSE by default, because a header a
     * client can set is not evidence of anything unless something in front strips and
     * rewrites it. Set {@code app.security.trust-proxy-headers=true} only when deployed
     * behind such a proxy.
     */
    @org.springframework.beans.factory.annotation.Value("${app.security.trust-proxy-headers:false}")
    private boolean trustProxyHeaders;

    private static final Duration MINUTE = Duration.ofMinutes(1);
    private static final Duration HOUR = Duration.ofHours(1);

    private final AuthService authService;
    private final PasswordResetService passwordResetService;

    public AuthController(AuthService authService, PasswordResetService passwordResetService, RateLimiter rateLimiter,
                          RateLimitProperties rateLimits) {
        this.rateLimiter = rateLimiter;
        this.rateLimits = rateLimits;
        this.authService = authService;
        this.passwordResetService = passwordResetService;
    }

    @PostMapping("/register")
    @SecurityRequirements  // public: creating an account cannot require an account
    @Operation(summary = "Create an account")
    public ResponseEntity<UserDto> register(@Valid @RequestBody RegisterRequest request,
                                            HttpServletRequest http) {
        rateLimiter.check("register", callerIp(http), rateLimits.registerPerHour(), HOUR);
        return ResponseEntity.status(HttpStatus.CREATED).body(authService.register(request));
    }

    @PostMapping("/login")
    @SecurityRequirements  // public: overrides the global bearer requirement in the docs
    @Operation(summary = "Authenticate and receive an access/refresh token pair")
    public AuthResponse login(
            @io.swagger.v3.oas.annotations.parameters.RequestBody(
                    content = @Content(
                            mediaType = "application/json",
                            examples = @ExampleObject(
                                    name = "Valid Credentials",
                                    value = "{\n  \"email\": \"user@example.com\",\n  \"password\": \"securepassword123\"\n}"
                            )
                    )
            )
            @Valid @RequestBody LoginRequest request, HttpServletRequest http) {
        rateLimiter.check("login", callerIp(http), rateLimits.loginPerMinute(), MINUTE);

        return authService.login(request);
    }

    @PostMapping("/refresh")
    @SecurityRequirements  // public: the refresh token IS the credential here
    @Operation(summary = "Exchange a refresh token for a new token pair (rotates the refresh token)")
    public AuthResponse refresh(@Valid @RequestBody RefreshTokenRequest request) {
        return authService.refresh(request.refreshToken());
    }

    @PostMapping("/forgot-password")
    @SecurityRequirements  // public: a user who cannot sign in must still reach this
    @Operation(summary = "Email a password reset link")
    public ResponseEntity<Void> forgotPassword(@Valid @RequestBody ForgotPasswordRequest request, HttpServletRequest http) {
        rateLimiter.check("password-reset", callerIp(http), rateLimits.passwordResetPerHour(), HOUR);
        passwordResetService.requestReset(request.email().trim().toLowerCase());

        // 202 unconditionally, whether or not the address has an account. Reporting
        // "no such user" would make this endpoint an account-existence oracle.
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/reset-password")
    @SecurityRequirements  // public: the reset token IS the credential here
    @Operation(summary = "Set a new password using an emailed reset token")
    public ResponseEntity<Void> resetPassword(@Valid @RequestBody ResetPasswordRequest request) {
        passwordResetService.resetPassword(request.token(), request.newPassword());
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/logout")
    @Operation(summary = "Revoke a single refresh token")
    public ResponseEntity<Void> logout(@Valid @RequestBody RefreshTokenRequest request) {
        authService.logout(request.refreshToken());
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/logout-all")
    @Operation(summary = "Revoke every refresh token belonging to the caller")
    public ResponseEntity<Void> logoutEverywhere(@CurrentUserId UUID userId) {
        authService.logoutEverywhere(userId);
        return ResponseEntity.noContent().build();
    }

    /**
     * The caller's address, for keying a limit on.
     *
     * <p><strong>{@code X-Forwarded-For} is read but only trusted behind a proxy that sets
     * it.</strong> A client can send that header itself, so taking it at face value on a
     * directly-exposed server lets an attacker defeat every IP limit here by varying one
     * string. This application binds localhost and sits behind nothing today, so the remote
     * address is the honest answer and the header is used only when a proxy is configured —
     * a deployment decision recorded in the production checklist, not guessed at here.
     *
     * <p>The first entry of the header is the original client; the rest are proxies.
     */
    private String callerIp(HttpServletRequest request) {
        if (trustProxyHeaders) {
            String forwarded = request.getHeader("X-Forwarded-For");
            if (forwarded != null && !forwarded.isBlank()) {
                return forwarded.split(",")[0].trim();
            }
        }
        String remote = request.getRemoteAddr();
        return remote == null ? "unknown" : remote;
    }
}
