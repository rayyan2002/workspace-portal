package com.bluestone.knowledge_assistant.auth;

import com.bluestone.knowledge_assistant.user.User;
import jakarta.persistence.*;

import java.time.Instant;
import java.util.UUID;

/**
 * A persisted, revocable refresh token.
 *
 * <p>{@code tokenHash} holds a SHA-256 digest, never the token itself — a leak of this
 * table must not yield usable credentials, the same reasoning that applies to passwords.
 */
@Entity
@Table(name = "refresh_tokens")
public class RefreshToken {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", updatable = false, nullable = false)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "token_hash", nullable = false, unique = true)
    private String tokenHash;

    @Column(name = "expires_at", nullable = false)
    private Instant expiresAt;

    @Column(name = "revoked_at")
    private Instant revokedAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected RefreshToken() {}

    public RefreshToken(User user, String tokenHash, Instant expiresAt, Instant createdAt) {
        this.user = user;
        this.tokenHash = tokenHash;
        this.expiresAt = expiresAt;
        this.createdAt = createdAt;
    }

    public UUID getId() { return id; }

    public User getUser() { return user; }

    public String getTokenHash() { return tokenHash; }

    public Instant getExpiresAt() { return expiresAt; }

    public Instant getRevokedAt() { return revokedAt; }

    public Instant getCreatedAt() { return createdAt; }

    public void revoke(Instant at) { this.revokedAt = at; }

    public boolean isRevoked() { return revokedAt != null; }

    public boolean isExpired(Instant now) { return expiresAt.isBefore(now); }

    /** Usable exactly when it is neither revoked nor past its expiry. */
    public boolean isUsable(Instant now) { return !isRevoked() && !isExpired(now); }
}
