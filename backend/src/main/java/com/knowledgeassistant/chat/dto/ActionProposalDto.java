package com.knowledgeassistant.chat.dto;

import java.util.Map;

public record ActionProposalDto(
        String id,
        String type,
        String label,
        Map<String, Object> payload,

        /**
         * The message this proposal belongs to — V23.
         *
         * <p>Lets the Actions page and the audit trail link to the exact prompt rather than
         * the conversation as a whole. Null on a freshly generated proposal only if it was
         * never persisted, which no longer happens.
         */
        java.util.UUID messageId,

        /**
         * What was already decided about this proposal, or null if nobody has decided yet.
         *
         * <p>THIS IS WHAT MAKES THE CARD PERMANENT. Proposals used to be ephemeral and the
         * decision lived in React state, so leaving the page lost it and a refresh removed
         * the card entirely — a decision a human made left no trace in the conversation
         * where they made it. History now replays both the proposal and its outcome.
         */
        Decision decision
) {

    /**
     * The outcome attached to a replayed proposal.
     *
     * @param decision      approved or rejected — what the human chose
     * @param status        what EXECUTION did: completed, failed, or running
     * @param result        the stored result, replayed verbatim; null unless completed
     * @param failureReason operator-facing text; null unless failed
     */
    public record Decision(String decision, String status, Object result, String failureReason) {}

    /** A freshly generated proposal: not yet attached to a stored message, not yet decided. */
    public static ActionProposalDto fresh(String id, String type, String label,
                                          Map<String, Object> payload) {
        return new ActionProposalDto(id, type, label, payload, null, null);
    }
}