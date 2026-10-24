package com.knowledgeassistant.action;

import com.knowledgeassistant.action.dto.ActionRequest;
import com.knowledgeassistant.action.dto.ActionResult;
import com.knowledgeassistant.action.dto.CreateTaskPayload;
import com.knowledgeassistant.chat.ChatSession;
import com.knowledgeassistant.genai.GenAiClient;
import com.knowledgeassistant.support.TestFixtures;
import com.knowledgeassistant.task.TaskPriority;
import com.knowledgeassistant.user.User;
import org.junit.jupiter.api.BeforeEach;
import tools.jackson.databind.ObjectMapper;
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
    @Autowired private ObjectMapper objectMapper;

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

        // UNTIL V21 THIS ASSERTED null, and that assertion was pinning a bug rather than a
        // guarantee. Approving a summarize takes about two minutes (134.9s measured), so a
        // user who navigated away mid-request destroyed the work permanently: the server
        // finished, nothing kept the answer, and clicking again produced a shrug. The
        // outcome is stored now, so the repeat replays it instead.
        assertNotNull(repeat.result(), "a repeated decision must replay the stored result");
    }

    @Test
    void theReplayedResultIsTheSameResult() {
        // Not merely non-null: the SAME answer. A replay that returned a different task,
        // or a freshly generated summary, would mean the side effect had run twice — which
        // is the thing idempotency exists to prevent.
        String actionId = "act-" + UUID.randomUUID();
        ActionResult first = actionService.processAction(approval(actionId), owner.getId());
        ActionResult repeat = actionService.processAction(approval(actionId), owner.getId());

        assertNotNull(first.result());
        // Compared AS JSON, not by toString. The live result is a TaskDto record and the
        // replayed one is a Map parsed back from storage, so their toStrings differ while
        // the payload is identical — and the JSON is what the client actually receives.
        // (That comparison also showed the wire name is `sourceSessionId`, not
        // `sessionId`, which is exactly the drift storing raw JSON avoids.)
        assertEquals(
                objectMapper.writeValueAsString(first.result()),
                objectMapper.writeValueAsString(repeat.result()),
                "the replay must carry the first execution's result, not a new one");
    }

    @Test
    void aRowDecidedBeforeTheResultWasStoredStillAnswers() {
        // Rows written before V21 have status and result NULL, and no backfill would be
        // anything but an invention. The replay must degrade to the old answer rather than
        // claim a result that was never kept.
        String actionId = "act-" + UUID.randomUUID();
        actionService.processAction(approval(actionId), owner.getId());

        ActionAudit stored = auditRepository.findByActionId(actionId).orElseThrow();
        stored.recordOutcome(null, null, null);          // as a pre-V21 row looks
        auditRepository.save(stored);

        ActionResult repeat = actionService.processAction(approval(actionId), owner.getId());

        assertEquals(ActionStatus.completed, repeat.status());
        assertNull(repeat.result(), "an unstored result must not be invented");
    }

    @Test
    void aReplayedDecisionSaysWhichDecisionActuallyStands() {
        // THE REPORTED BUG. A user approved a create-task proposal, then pressed Reject on
        // the same card, and the card answered "Task created: University admission policy."
        // The server was right — rejecting afterwards must not delete a task that exists —
        // but the UI reported a creation as though the Reject click had caused it.
        String actionId = "act-" + UUID.randomUUID();
        actionService.processAction(approval(actionId), owner.getId());

        ActionRequest lateRejection = new ActionRequest(actionId, session.getId(),
                ActionDecision.rejected, ActionType.CREATE_TASK,
                new CreateTaskPayload("Review the runway findings", TaskPriority.medium));
        ActionResult replay = actionService.processAction(lateRejection, owner.getId());

        assertEquals(ActionDecision.approved, replay.replayedDecision(),
                "a replay must name the decision that actually stands");
        assertEquals(ActionStatus.completed, replay.status());
        assertEquals(1, fixtures.taskCount(owner), "the rejection must not undo the task");
    }

    @Test
    void aDecisionMadeNowIsNotMarkedAsAReplay() {
        // The other half: without this, the client would show "already decided" on every
        // first click and the field would be useless.
        ActionResult first = actionService.processAction(
                approval("act-" + UUID.randomUUID()), owner.getId());

        assertNull(first.replayedDecision(),
                "the call that decides a proposal is not replaying anything");
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
                new com.knowledgeassistant.action.dto.LookupPayload("anything"));

        ActionResult accepted = actionService.processAction(lookup, owner.getId());

        // V22: lookup calls a language model, so the DECISION is acknowledged immediately
        // and the work finishes in the background. The audit row carries the outcome.
        assertEquals(ActionStatus.running, accepted.status());

        ActionAudit outcome = auditRepository.findByActionId(lookup.actionId()).orElseThrow();
        assertEquals(ActionStatus.failed, outcome.getStatus());
        assertNull(outcome.getResult(), "a failure stores no result");
    }
}
