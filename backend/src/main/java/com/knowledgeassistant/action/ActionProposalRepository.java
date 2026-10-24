package com.knowledgeassistant.action;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ActionProposalRepository extends JpaRepository<ActionProposal, String> {

    /**
     * Every proposal for a page of messages, in ONE query.
     *
     * <p>Per-message lookups would be the N+1 that QueryCountTest exists to catch — history
     * loads a whole page of messages at a time.
     */
    List<ActionProposal> findByMessageIdIn(List<UUID> messageIds);

    Optional<ActionProposal> findByActionId(String actionId);

    /** Message ids for a page of actions in ONE query — the audit trail and the task list
     *  both resolve their deep links this way. */
    List<ActionProposal> findByActionIdIn(List<String> actionIds);
}
