package com.bluestone.knowledge_assistant.chat;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface MessageRepository extends JpaRepository<Message, UUID> {
    // Utilizes the composite index (session_id, created_at) from Day 3
    List<Message> findBySessionIdOrderByCreatedAtAsc(UUID sessionId);
}