package com.bluestone.knowledge_assistant.auth;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface PasswordResetTokenRepository extends JpaRepository<PasswordResetToken, UUID> {

    /** Lookup is by digest, because the plaintext token is never stored. */
    Optional<PasswordResetToken> findByTokenHash(String tokenHash);

    /**
     * Invalidates any outstanding tokens for a user. Called when a new reset is
     * requested, so that requesting twice cannot leave two live tokens in two inboxes,
     * and again after a successful reset.
     */
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
            UPDATE PasswordResetToken t
            SET t.usedAt = :now
            WHERE t.user.id = :userId AND t.usedAt IS NULL
            """)
    int invalidateAllForUser(@Param("userId") UUID userId, @Param("now") Instant now);
}
