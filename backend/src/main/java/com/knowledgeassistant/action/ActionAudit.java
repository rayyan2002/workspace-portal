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

    /**
     * What EXECUTION did, as opposed to what the user decided — V21.
     *
     * <p>These are different facts and conflating them was a bug: the idempotency branch
     * inferred the status from the decision, so replaying an APPROVED action that had
     * FAILED reported success.
     *
     * <p>NULL for rows written before V21. There is no backfill that would not be an
     * invention, so those rows keep the old behaviour.
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "status")
    private ActionStatus status;

    /**
     * The result JSON exactly as the API returned it.
     *
     * <p>Stored because approving a summarize-document action takes about two minutes — one
     * measured run was 134.9 seconds — and a user who navigates away mid-request used to
     * destroy that work permanently. Replaying now returns the answer instead of a shrug.
     *
     * <p>TEXT rather than a mapped object graph: what is wanted back is the exact bytes the
     * client would have received, and re-deriving them through a DTO would let the stored
     * shape drift from the live one without anything noticing.
     */
    @Column(name = "result")
    private String result;

    /** Operator-facing text, never document content. Only set when status is failed. */
    @Column(name = "failure_reason")
    private String failureReason;

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
    public ActionStatus getStatus() { return status; }
    public String getResult() { return result; }
    public String getFailureReason() { return failureReason; }

    /**
     * Records what execution produced. Called once, AFTER the side effect, which is why
     * these are not constructor arguments: the audit row is written BEFORE execution so
     * the unique constraint can stop a double-click, and the outcome is not known yet.
     */
    public void recordOutcome(ActionStatus status, String result, String failureReason) {
        this.status = status;
        this.result = result;
        this.failureReason = failureReason;
    }
}