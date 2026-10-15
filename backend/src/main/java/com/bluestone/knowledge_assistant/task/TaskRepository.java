package com.bluestone.knowledge_assistant.task;

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
public interface TaskRepository extends JpaRepository<Task, UUID> {

    // --- Ownership by JOIN ---------------------------------------------------
    // 'tasks' has no user_id column; a task belongs to whoever owns the chat session
    // it was created from (tasks.source_session_id -> chat_sessions.user_id). Because
    // Task models sourceSessionId as a plain UUID rather than a @ManyToOne, these use
    // an explicit ad-hoc JOIN ... ON rather than a derived query.

    @Query("""
            SELECT t FROM Task t
            JOIN ChatSession s ON t.sourceSessionId = s.id
            WHERE s.user.id = :userId
            """)
    List<Task> findByOwner(@Param("userId") UUID userId);

    // countQuery supplied explicitly: Spring Data cannot always derive a correct COUNT
    // from a JPQL query with an explicit join, and a wrong total silently breaks the
    // pager rather than failing loudly.
    @Query(value = """
            SELECT t FROM Task t
            JOIN ChatSession s ON t.sourceSessionId = s.id
            WHERE s.user.id = :userId
            ORDER BY t.createdAt DESC
            """,
            countQuery = """
            SELECT count(t) FROM Task t
            JOIN ChatSession s ON t.sourceSessionId = s.id
            WHERE s.user.id = :userId
            """)
    Page<Task> findByOwner(@Param("userId") UUID userId, Pageable pageable);

    @Query(value = """
            SELECT t FROM Task t
            JOIN ChatSession s ON t.sourceSessionId = s.id
            WHERE s.user.id = :userId AND t.status = :status
            ORDER BY t.createdAt DESC
            """,
            countQuery = """
            SELECT count(t) FROM Task t
            JOIN ChatSession s ON t.sourceSessionId = s.id
            WHERE s.user.id = :userId AND t.status = :status
            """)
    Page<Task> findByOwnerAndStatus(@Param("userId") UUID userId,
                                    @Param("status") TaskStatus status,
                                    Pageable pageable);

    @Query("""
            SELECT t FROM Task t
            JOIN ChatSession s ON t.sourceSessionId = s.id
            WHERE s.user.id = :userId AND t.status = :status
            """)
    List<Task> findByOwnerAndStatus(@Param("userId") UUID userId, @Param("status") TaskStatus status);

    /** Single-task lookup that resolves only if the caller owns it — the 404-not-403 path. */
    @Query("""
            SELECT t FROM Task t
            JOIN ChatSession s ON t.sourceSessionId = s.id
            WHERE t.id = :taskId AND s.user.id = :userId
            """)
    Optional<Task> findByIdAndOwner(@Param("taskId") UUID taskId, @Param("userId") UUID userId);
}
