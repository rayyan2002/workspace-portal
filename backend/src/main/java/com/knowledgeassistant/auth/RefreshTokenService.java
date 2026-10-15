package com.knowledgeassistant.auth;

import com.knowledgeassistant.common.UnauthorizedException;
import com.knowledgeassistant.security.jwt.JwtProperties;
import com.knowledgeassistant.user.User;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.UUID;

/**
 * Issues, rotates, and revokes refresh tokens.
 *
 * <p>Rotation is single-use: redeeming a refresh token revokes it and issues a new one.
 * That turns a stolen token into a race the attacker has to win, and makes reuse of an
 * already-redeemed token detectable — which is treated as compromise and revokes the
 * user's whole token family.
 */
@Service
public class RefreshTokenService {

    private static final Logger log = LoggerFactory.getLogger(RefreshTokenService.class);

    /** 256 bits of entropy, URL-safe. Guessing is not a realistic attack at this size. */
    private static final int TOKEN_BYTES = 32;

    private final RefreshTokenRepository refreshTokenRepository;
    private final JwtProperties jwtProperties;
    private final SecureRandom secureRandom = new SecureRandom();

    /**
     * Runs the compromise response in its OWN transaction.
     *
     * <p>Necessary because reuse detection both revokes and throws: without a separate
     * transaction the thrown {@link UnauthorizedException} rolls the caller's transaction
     * back and silently undoes the revocation, leaving the stolen family live.
     */
    private final TransactionTemplate requiresNewTransaction;

    public RefreshTokenService(RefreshTokenRepository refreshTokenRepository,
                               JwtProperties jwtProperties,
                               PlatformTransactionManager transactionManager) {
        this.refreshTokenRepository = refreshTokenRepository;
        this.jwtProperties = jwtProperties;
        this.requiresNewTransaction = new TransactionTemplate(transactionManager);
        this.requiresNewTransaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    /**
     * Creates a new refresh token for a user.
     *
     * @return the PLAINTEXT token — this is the only moment it exists in readable form.
     *         Only its digest is persisted.
     */
    @Transactional
    public String issue(User user) {
        byte[] raw = new byte[TOKEN_BYTES];
        secureRandom.nextBytes(raw);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(raw);

        Instant now = Instant.now();
        RefreshToken entity = new RefreshToken(
                user,
                hash(token),
                now.plus(jwtProperties.refreshTokenTtl()),
                now);

        refreshTokenRepository.save(entity);
        return token;
    }

    /**
     * Validates and consumes a refresh token, returning the owning user.
     *
     * <p>The caller is expected to issue a replacement via {@link #issue(User)} — this
     * method has already revoked the one presented.
     */
    @Transactional
    public User consume(String presentedToken) {
        Instant now = Instant.now();

        RefreshToken stored = refreshTokenRepository.findByTokenHash(hash(presentedToken))
                .orElseThrow(() -> new UnauthorizedException("Invalid refresh token"));

        if (stored.isRevoked()) {
            // A revoked token being presented means either a replay of an already-rotated
            // token or a stolen one. Either way the family is no longer trustworthy.
            UUID compromisedUserId = stored.getUser().getId();
            log.warn("Refresh token reuse detected for user {} — revoking all their tokens", compromisedUserId);

            // Committed independently, so that the exception below cannot roll it back.
            requiresNewTransaction.executeWithoutResult(status ->
                    refreshTokenRepository.revokeAllForUser(compromisedUserId, now));

            throw new UnauthorizedException("Invalid refresh token");
        }

        if (stored.isExpired(now)) {
            throw new UnauthorizedException("Refresh token has expired");
        }

        stored.revoke(now);
        return stored.getUser();
    }

    /** Single-session logout: invalidates just the token the caller presented. */
    @Transactional
    public void revoke(String presentedToken) {
        refreshTokenRepository.findByTokenHash(hash(presentedToken))
                .filter(token -> !token.isRevoked())
                .ifPresent(token -> token.revoke(Instant.now()));
    }

    /** Logout everywhere: invalidates every live token the user holds. */
    @Transactional
    public int revokeAllForUser(UUID userId) {
        return refreshTokenRepository.revokeAllForUser(userId, Instant.now());
    }

    private String hash(String token) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(token.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            // SHA-256 is mandated by the JDK spec; this cannot happen on a valid runtime.
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
