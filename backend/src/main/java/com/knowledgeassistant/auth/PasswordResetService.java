package com.knowledgeassistant.auth;

import com.knowledgeassistant.common.UnauthorizedException;
import com.knowledgeassistant.mail.EmailService;
import com.knowledgeassistant.user.User;
import com.knowledgeassistant.user.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;

/**
 * Password reset by emailed one-time link.
 */
@Service
public class PasswordResetService {

    private static final Logger log = LoggerFactory.getLogger(PasswordResetService.class);

    private static final int TOKEN_BYTES = 32;               // 256 bits
    private static final Duration TOKEN_TTL = Duration.ofMinutes(30);

    private final PasswordResetTokenRepository tokenRepository;
    private final RefreshTokenService refreshTokenService;
    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final EmailService emailService;
    private final SecureRandom secureRandom = new SecureRandom();

    private final String frontendBaseUrl;

    public PasswordResetService(PasswordResetTokenRepository tokenRepository,
                                RefreshTokenService refreshTokenService,
                                UserRepository userRepository,
                                PasswordEncoder passwordEncoder,
                                EmailService emailService,
                                @Value("${app.frontend.base-url}") String frontendBaseUrl) {
        this.tokenRepository = tokenRepository;
        this.refreshTokenService = refreshTokenService;
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.emailService = emailService;
        this.frontendBaseUrl = frontendBaseUrl;
    }

    /**
     * Emails a reset link, if the address belongs to an account.
     *
     * <p>Returns normally either way and says nothing about whether the account exists.
     * A "no such user" response here would turn this endpoint into an account-existence
     * oracle, undoing the anti-enumeration care taken on login.
     */
    @Transactional
    public void requestReset(String email) {
        userRepository.findByEmail(email).ifPresentOrElse(
                this::issueAndSend,
                () -> log.info("Password reset requested for an address with no account; nothing sent"));
    }

    private void issueAndSend(User user) {
        Instant now = Instant.now();

        // Requesting a second reset invalidates the first. Otherwise two live links
        // would sit in the inbox and the older one would still work.
        tokenRepository.invalidateAllForUser(user.getId(), now);

        byte[] raw = new byte[TOKEN_BYTES];
        secureRandom.nextBytes(raw);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(raw);

        tokenRepository.save(new PasswordResetToken(user, hash(token), now.plus(TOKEN_TTL), now));

        String link = frontendBaseUrl + "/reset-password?token="
                + URLEncoder.encode(token, StandardCharsets.UTF_8);

        emailService.send(user.getEmail(), "Reset your Knowledge Assistant password", """
                Hi %s,

                We received a request to reset your Knowledge Assistant password.
                Open the link below to choose a new one:

                %s

                This link expires in %d minutes and can only be used once.

                If you did not request this, you can ignore this email — your password
                will not change and no one has access to your account.
                """.formatted(
                user.getName() == null ? "there" : user.getName(),
                link,
                TOKEN_TTL.toMinutes()));
    }

    /**
     * Consumes a reset token and sets the new password.
     *
     * <p>Every refresh token for the account is revoked as part of this. A password
     * reset is the action someone takes when they believe their account is compromised;
     * leaving existing sessions alive would mean the attacker keeps their access and
     * the reset accomplishes nothing.
     */
    @Transactional
    public void resetPassword(String presentedToken, String newPassword) {
        Instant now = Instant.now();

        PasswordResetToken stored = tokenRepository.findByTokenHash(hash(presentedToken))
                .orElseThrow(() -> new UnauthorizedException("This reset link is invalid or has already been used."));

        if (stored.isUsed()) {
            throw new UnauthorizedException("This reset link is invalid or has already been used.");
        }

        if (stored.isExpired(now)) {
            throw new UnauthorizedException("This reset link has expired. Request a new one.");
        }

        User user = stored.getUser();
        user.setPassword(passwordEncoder.encode(newPassword));

        stored.markUsed(now);
        tokenRepository.invalidateAllForUser(user.getId(), now);
        refreshTokenService.revokeAllForUser(user.getId());

        log.info("Password reset completed for user {}; all sessions revoked", user.getId());
    }

    private String hash(String token) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(token.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
