package com.knowledgeassistant.action;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface ActionAuditRepository extends JpaRepository<ActionAudit, UUID> {

    /**
     * The decision already recorded for a proposal, if there is one.
     *
     * <p>Used to make a repeated approval IDEMPOTENT rather than an error. A double-click or
     * a retried request should return what the first decision produced, not a 500 and not a
     * second task. V20 makes a second row impossible; this is how the second REQUEST is
     * answered.
     */
    Optional<ActionAudit> findByActionId(String actionId);


    /**
     * The caller's audit trail only. Same JOIN shape as tasks: an audit row belongs to
     * whoever owns the session it was recorded against. Sorting moved into the query —
     * it was being done in Java over every row in the table.
     */
    @Query("""
            SELECT a FROM ActionAudit a
            JOIN ChatSession s ON a.sessionId = s.id
            WHERE s.user.id = :userId
            ORDER BY a.createdAt DESC
            """)
    List<ActionAudit> findByOwnerOrderByCreatedAtDesc(@Param("userId") UUID userId);

    @Query(value = """
            SELECT a FROM ActionAudit a
            JOIN ChatSession s ON a.sessionId = s.id
            WHERE s.user.id = :userId
            ORDER BY a.createdAt DESC
            """,
            countQuery = """
            SELECT count(a) FROM ActionAudit a
            JOIN ChatSession s ON a.sessionId = s.id
            WHERE s.user.id = :userId
            """)
    Page<ActionAudit> findByOwnerOrderByCreatedAtDesc(@Param("userId") UUID userId, Pageable pageable);
}
