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
public interface RefreshTokenRepository extends JpaRepository<RefreshToken, UUID> {

    /** Lookup is by digest, because the plaintext token is never stored. */
    Optional<RefreshToken> findByTokenHash(String tokenHash);

    /**
     * Revokes every live token for a user in one statement — used on "log out everywhere"
     * and on reuse detection, where the safe response is to invalidate the whole family.
     */
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
            UPDATE RefreshToken r
            SET r.revokedAt = :now
            WHERE r.user.id = :userId AND r.revokedAt IS NULL
            """)
    int revokeAllForUser(@Param("userId") UUID userId, @Param("now") Instant now);

    /** Housekeeping: rows that can never be used again are just clutter. */
    @Modifying
    @Query("DELETE FROM RefreshToken r WHERE r.expiresAt < :cutoff")
    int deleteExpiredBefore(@Param("cutoff") Instant cutoff);
}
