package com.bluestone.knowledge_assistant.chat;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface ChatSessionRepository extends JpaRepository<ChatSession, UUID> {

    // Traverses the @ManyToOne 'user' relationship and orders by the denormalized timestamp
    List<ChatSession> findByUser_IdOrderByUpdatedAtDesc(UUID userId);

    Page<ChatSession> findByUser_IdOrderByUpdatedAtDesc(UUID userId, Pageable pageable);

    // --- Ownership folded INTO the lookup, not checked after it ---------------
    // There is deliberately no findById(..) + compare-owner path here. Loading a row
    // you are not entitled to and then deciding what to do with it leaves a window
    // where the wrong data is in hand; making ownership part of the WHERE clause
    // means an unauthorized id simply does not resolve, and the 404 (not 403 —
    // a 403 would confirm the id exists) falls out for free.

    Optional<ChatSession> findByIdAndUser_Id(UUID id, UUID userId);

    boolean existsByIdAndUser_Id(UUID id, UUID userId);
}
