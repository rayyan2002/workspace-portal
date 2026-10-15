package com.bluestone.knowledge_assistant.action;

import com.bluestone.knowledge_assistant.action.dto.ActionRequest;
import com.bluestone.knowledge_assistant.action.dto.ActionResult;
import com.bluestone.knowledge_assistant.action.dto.CreateTaskPayload;
import com.bluestone.knowledge_assistant.chat.ChatSession;
import com.bluestone.knowledge_assistant.genai.GenAiClient;
import com.bluestone.knowledge_assistant.support.TestFixtures;
import com.bluestone.knowledge_assistant.task.TaskPriority;
import com.bluestone.knowledge_assistant.user.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

/**
 * Day 11: a proposal is decided once.
 *
 * <p>This is not a hypothetical guard. Before V20 the live database contained five proposals
 * decided twice — two {@code approved + approved} (two tasks from one click) and one
 * {@code rejected + approved}, where a human declined an action and it ran anyway. There
 * were duplicate task rows to match. A double-click, a retried request or a back-button was
 * enough, because {@code action_audit} had no uniqueness on {@code action_id}.
 */
@SpringBootTest
@ActiveProfiles("test")
@Transactional
class ActionIdempotencyTest {

    @MockitoBean private GenAiClient genAiClient;
    @Autowired private ActionService actionService;
    @Autowired private ActionAuditRepository auditRepository;
    @Autowired private TestFixtures fixtures;

    private User owner;
    private ChatSession session;

    @BeforeEach
    void setUp() {
        owner = fixtures.user();
        session = fixtures.session(owner, "Actions");
    }

    private ActionRequest approval(String actionId) {
        return new ActionRequest(actionId, session.getId(), ActionDecision.approved,
                ActionType.CREATE_TASK,
                new CreateTaskPayload("Review the runway findings", TaskPriority.medium));
    }

    @Test
    void approvingTwiceCreatesOneTask_notTwo() {
        String actionId = "act-" + UUID.randomUUID();

        ActionResult first = actionService.processAction(approval(actionId), owner.getId());
        long afterFirst = fixtures.taskCount(owner);

        ActionResult second = actionService.processAction(approval(actionId), owner.getId());
        long afterSecond = fixtures.taskCount(owner);

        assertEquals(1, afterFirst);
        assertEquals(1, afterSecond, "a repeated approval must not create a second task");
        assertEquals(ActionStatus.completed, first.status());
        assertEquals(ActionStatus.completed, second.status(),
                "the repeat reports what the first decision produced");
    }

    @Test
    void theRepeatIsNotAnError_becauseADoubleClickIsNotAnError() {
        String actionId = "act-" + UUID.randomUUID();
        actionService.processAction(approval(actionId), owner.getId());

        // Returns the original outcome rather than throwing or 409-ing. That is what
        // "idempotent" means: the caller sees what it would have seen the first time.
        ActionResult repeat = actionService.processAction(approval(actionId), owner.getId());

        assertNotNull(repeat);
        assertEquals(ActionStatus.completed, repeat.status());
        // The first side effect is not replayed and its result was never stored, so there is
        // nothing truthful to return here. Null is honest; re-running to regenerate it would
        // defeat the point.
        assertNull(repeat.result());
    }

    @Test
    void aRejectionCannotLaterBeApproved() {
        // The worst of the five rows found in the live database: a human declined an action
        // and the same action was approved afterwards. The refusal must stand.
        String actionId = "act-" + UUID.randomUUID();
        ActionRequest rejection = new ActionRequest(actionId, session.getId(),
                ActionDecision.rejected, ActionType.CREATE_TASK,
                new CreateTaskPayload("Review the runway findings", TaskPriority.medium));

        actionService.processAction(rejection, owner.getId());
        ActionResult sneakyApproval = actionService.processAction(approval(actionId), owner.getId());

        assertEquals(ActionStatus.rejected, sneakyApproval.status(),
                "an approval after a rejection must not execute");
        assertEquals(0, fixtures.taskCount(owner), "the rejected action must not have run");
    }

    @Test
    void exactlyOneAuditRowSurvivesPerProposal() {
        String actionId = "act-" + UUID.randomUUID();
        actionService.processAction(approval(actionId), owner.getId());
        actionService.processAction(approval(actionId), owner.getId());
        actionService.processAction(approval(actionId), owner.getId());

        assertEquals(1, auditRepository.findAll().stream()
                .filter(a -> actionId.equals(a.getActionId())).count());
    }

    @Test
    void lookupKnowledgeReportsFailed_ratherThanFalselyCompleted() {
        // It returned "Placeholder logic: Queried knowledge base." and reported `completed` —
        // the UI told the user an action had succeeded when nothing had run. ActionStatus
        // had a `failed` value that nothing could produce (BACKLOG.md item 4); now it can.
        ActionRequest lookup = new ActionRequest("act-" + UUID.randomUUID(), session.getId(),
                ActionDecision.approved, ActionType.LOOKUP_KNOWLEDGE,
                new com.bluestone.knowledge_assistant.action.dto.LookupPayload("anything"));

        ActionResult result = actionService.processAction(lookup, owner.getId());

        assertEquals(ActionStatus.failed, result.status());
        assertNull(result.result());
    }
}
