package com.knowledgeassistant.auth;

import com.knowledgeassistant.user.User;
import jakarta.persistence.*;

import java.time.Instant;
import java.util.UUID;

/**
 * A single-use, short-lived credential that can set a new password.
 *
 * <p>Stored as a SHA-256 digest, never in the clear: anyone holding the raw value can
 * take over the account, which makes it every bit as sensitive as the password itself.
 */
@Entity
@Table(name = "password_reset_tokens")
public class PasswordResetToken {

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

    @Column(name = "used_at")
    private Instant usedAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected PasswordResetToken() {}

    public PasswordResetToken(User user, String tokenHash, Instant expiresAt, Instant createdAt) {
        this.user = user;
        this.tokenHash = tokenHash;
        this.expiresAt = expiresAt;
        this.createdAt = createdAt;
    }

    public UUID getId() { return id; }

    public User getUser() { return user; }

    public Instant getExpiresAt() { return expiresAt; }

    public Instant getUsedAt() { return usedAt; }

    public boolean isUsed() { return usedAt != null; }

    public boolean isExpired(Instant now) { return expiresAt.isBefore(now); }

    public void markUsed(Instant at) { this.usedAt = at; }
}
