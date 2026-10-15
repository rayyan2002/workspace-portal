package com.knowledgeassistant.action;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "action_audit")
public class ActionAudit {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", updatable = false, nullable = false)
    private UUID id;

    // Changed from UUID to String to match the VARCHAR column in PostgreSQL
    @Column(name = "action_id", nullable = false)
    private String actionId;

    @Column(name = "session_id", nullable = false)
    private UUID sessionId;

    //@Enumerated(EnumType.STRING)
    @Column(name = "type", nullable = false)
    private ActionType type;

    @Enumerated(EnumType.STRING)
    @Column(name = "decision", nullable = false)
    private ActionDecision decision;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected ActionAudit() {}

    public ActionAudit(String actionId, UUID sessionId, ActionType type, ActionDecision decision, Instant createdAt) {
        this.actionId = actionId;
        this.sessionId = sessionId;
        this.type = type;
        this.decision = decision;
        this.createdAt = createdAt;
    }

    // --- Getters ---
    public UUID getId() { return id; }
    public String getActionId() { return actionId; }
    public UUID getSessionId() { return sessionId; }
    public ActionType getType() { return type; }
    public ActionDecision getDecision() { return decision; }
    public Instant getCreatedAt() { return createdAt; }
}