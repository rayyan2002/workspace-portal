package com.knowledgeassistant.action;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;
import java.util.UUID;

/**
 * What the model proposed, kept — V23.
 *
 * <p>Proposals used to be ephemeral: built when the reply was generated, sent once, never
 * stored. Two reported problems came from that single fact. The card vanished on refresh,
 * so a decision a human made left no trace in the conversation where they made it. And
 * nothing linked an audit row or a task back to the message that caused it, because the
 * proposal is the thing that sits between the two.
 */
@Entity
@Table(name = "action_proposals")
public class ActionProposal {

    /** The action id itself. Not a surrogate — the id IS the identity, as action_audit assumes. */
    @Id
    @Column(name = "action_id", updatable = false, nullable = false)
    private String actionId;

    @Column(name = "message_id", nullable = false)
    private UUID messageId;

    @Column(name = "session_id", nullable = false)
    private UUID sessionId;

    @Column(name = "type", nullable = false)
    private ActionType type;

    /** As the proposer produced it. Stored rather than re-derived, so it cannot drift from
     *  the text the user actually saw and decided on. */
    @Column(name = "label", nullable = false)
    private String label;

    /** Payload JSON exactly as sent to the client. */
    @Column(name = "payload", nullable = false)
    private String payload;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected ActionProposal() {}

    public ActionProposal(String actionId, UUID messageId, UUID sessionId, ActionType type,
                          String label, String payload, Instant createdAt) {
        this.actionId = actionId;
        this.messageId = messageId;
        this.sessionId = sessionId;
        this.type = type;
        this.label = label;
        this.payload = payload;
        this.createdAt = createdAt;
    }

    public String getActionId() { return actionId; }
    public UUID getMessageId() { return messageId; }
    public UUID getSessionId() { return sessionId; }
    public ActionType getType() { return type; }
    public String getLabel() { return label; }
    public String getPayload() { return payload; }
    public Instant getCreatedAt() { return createdAt; }
}
