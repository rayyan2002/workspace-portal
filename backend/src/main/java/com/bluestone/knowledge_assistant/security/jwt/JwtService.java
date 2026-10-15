package com.bluestone.knowledge_assistant.security.jwt;

import com.bluestone.knowledge_assistant.security.userdetails.UserPrincipal;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.ExpiredJwtException;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Service;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * Issues and verifies stateless access tokens.
 *
 * <p>Only access tokens are JWTs. Refresh tokens are opaque and live in the database —
 * see {@code RefreshTokenService} — because a JWT you cannot revoke is the wrong tool
 * for the one credential that must survive long enough to need revoking.
 */
@Service
public class JwtService {

    private static final Logger log = LoggerFactory.getLogger(JwtService.class);

    private static final String CLAIM_EMAIL = "email";
    private static final String CLAIM_ROLES = "roles";

    private final JwtProperties properties;
    private final SecretKey signingKey;

    public JwtService(JwtProperties properties) {
        this.properties = properties;
        this.signingKey = Keys.hmacShaKeyFor(properties.secret().getBytes(StandardCharsets.UTF_8));
    }

    /** Mints a signed access token carrying the user's id, email, and authorities. */
    public String generateAccessToken(UserPrincipal principal) {
        Instant now = Instant.now();
        Instant expiry = now.plus(properties.accessTokenTtl());

        List<String> roles = principal.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList();

        return Jwts.builder()
                .subject(principal.getId().toString())
                .issuer(properties.issuer())
                .issuedAt(Date.from(now))
                .expiration(Date.from(expiry))
                .claim(CLAIM_EMAIL, principal.getUsername())
                .claim(CLAIM_ROLES, roles)
                .signWith(signingKey)
                .compact();
    }

    public Duration accessTokenTtl() {
        return properties.accessTokenTtl();
    }

    /**
     * Verifies signature, issuer, and expiry, returning the claims only if all hold.
     *
     * <p>Returns empty rather than throwing: an invalid token is an expected condition on
     * a public endpoint, not an exceptional one, and the filter's job is simply to leave
     * the security context empty so the entry point can answer 401.
     */
    public Optional<Claims> parse(String token) {
        try {
            Claims claims = Jwts.parser()
                    .verifyWith(signingKey)
                    .requireIssuer(properties.issuer())
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
            return Optional.of(claims);
        } catch (ExpiredJwtException e) {
            log.debug("Rejected expired JWT for subject {}", e.getClaims().getSubject());
            return Optional.empty();
        } catch (JwtException | IllegalArgumentException e) {
            // Bad signature, wrong issuer, malformed, unsupported algorithm, empty string.
            log.debug("Rejected invalid JWT: {}", e.getMessage());
            return Optional.empty();
        }
    }

    public UUID extractUserId(Claims claims) {
        return UUID.fromString(claims.getSubject());
    }
}
