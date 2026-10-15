package com.knowledgeassistant.chat;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "messages")
public class Message {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", updatable = false, nullable = false)
    private UUID id;

    // Raw UUID mapping instead of @ManyToOne to avoid lazy-loading overhead
    @Column(name = "session_id", nullable = false)
    private UUID sessionId;

    @Column(name = "content", nullable = false, columnDefinition = "TEXT")
    private String content;

    @Enumerated(EnumType.STRING)
    @Column(name = "sender", nullable = false)
    private MessageSender sender;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Message() {}

    public Message(UUID sessionId, String content, MessageSender sender, Instant createdAt) {
        this.sessionId = sessionId;
        this.content = content;
        this.sender = sender;
        this.createdAt = createdAt;
    }

    public UUID getId() { return id; }
    public UUID getSessionId() { return sessionId; }
    public String getContent() { return content; }
    public MessageSender getSender() { return sender; }
    public Instant getCreatedAt() { return createdAt; }
}