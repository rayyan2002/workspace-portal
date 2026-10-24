package com.knowledgeassistant.action;

import com.knowledgeassistant.action.dto.ActionRequest;
import com.knowledgeassistant.action.dto.ActionResult;
import com.knowledgeassistant.action.dto.SummarizeResult;
import com.knowledgeassistant.action.dto.SummarizePayload;
import com.knowledgeassistant.chat.ChatSession;
import com.knowledgeassistant.document.Document;
import com.knowledgeassistant.genai.GenAiClient;
import com.knowledgeassistant.genai.GenAiUnavailableException;
import com.knowledgeassistant.genai.dto.GenAiAnswerResponse;
import com.knowledgeassistant.support.TestFixtures;
import com.knowledgeassistant.user.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.ArgumentMatchers;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Day 11's "done when": an approved tool call can produce a document summary.
 *
 * <p>Summarising reuses {@code POST /answer} rather than adding an endpoint, so the
 * allow-list, the grounding guard and insufficient-context handling all apply unchanged.
 */
@SpringBootTest
@ActiveProfiles("test")
@Transactional
class ActionSummarizeTest {

    @MockitoBean private GenAiClient genAiClient;
    @Autowired private ActionService actionService;
    @Autowired private TestFixtures fixtures;
    @Autowired private ActionAuditRepository auditRepository;

    /**
     * The outcome of a summarise, read from where it now lives.
     *
     * <p>V22 moved slow work off the request: approving returns `running` immediately and
     * the audit row carries the terminal status. Asserting on the returned value would only
     * ever see `running` and would say nothing about whether the work succeeded.
     */
    private ActionAudit outcomeOf(String actionId) {
        return auditRepository.findByActionId(actionId).orElseThrow();
    }

    private User owner;
    private ChatSession session;
    private Document document;

    @BeforeEach
    void setUp() {
        owner = fixtures.user();
        session = fixtures.session(owner, "Summaries");
        document = fixtures.document(owner, "report.txt");
    }

    private ActionRequest approveSummary(UUID documentId) {
        return new ActionRequest("act-" + UUID.randomUUID(), session.getId(),
                ActionDecision.approved, ActionType.SUMMARIZE_DOCUMENT,
                new SummarizePayload(documentId, "report.txt"));
    }

    @Test
    void anApprovedSummaryReturnsTheGeneratedText() {
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenReturn(new GenAiAnswerResponse("grounded",
                        "The report covers quarterly runway inspections.", List.of(), List.of(), null));

        ActionRequest request = approveSummary(document.getId());
        ActionResult accepted = actionService.processAction(request, owner.getId());

        // The REQUEST is answered the moment the decision is recorded — V22. Holding the
        // connection open for the two minutes the model takes is what made people navigate
        // away from a working system.
        assertEquals(ActionStatus.running, accepted.status());

        // The OUTCOME lives on the audit row.
        ActionAudit outcome = outcomeOf(request.actionId());
        assertEquals(ActionStatus.completed, outcome.getStatus());
        // Wrapped in SummarizeResult since Day 14b, and the wrapper is not cosmetic: the
        // frontend's ActionResult union declares `result: { summary: string }` and
        // ActionCard.tsx renders `result.summary`, which against a bare string is
        // `undefined` — an approved summary rendered as an empty card.
        assertTrue(outcome.getResult().contains("quarterly runway inspections"),
                "the stored result must carry the summary text");
        assertTrue(outcome.getResult().contains("summary"),
                "and must keep the SummarizeResult wrapper the frontend reads");
    }

    @Test
    void theSummaryIsScopedToExactlyOneDocument() {
        // "Summarise this document" must not quietly draw on every other document the user
        // owns. The allow-list sent is the one document, not the caller's whole corpus.
        fixtures.document(owner, "unrelated.txt");
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenReturn(new GenAiAnswerResponse("grounded", "A summary.", List.of(), List.of(), null));

        actionService.processAction(approveSummary(document.getId()), owner.getId());

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<UUID>> allowed = ArgumentCaptor.forClass(List.class);
        Mockito.verify(genAiClient).answer(ArgumentMatchers.anyString(), allowed.capture(),
                ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any());

        assertEquals(List.of(document.getId()), allowed.getValue());
    }

    @Test
    void anotherUsersDocumentCannotBeSummarised() {
        // The request arrives from a browser naming a documentId. Trusting it would let
        // anyone summarise any document by editing the payload.
        User stranger = fixtures.user();
        Document theirs = fixtures.document(stranger, "private.txt");

        ActionRequest request = approveSummary(theirs.getId());
        actionService.processAction(request, owner.getId());

        // Accepted instantly, failed in the background — V22. The row is the record.
        assertEquals(ActionStatus.failed, outcomeOf(request.actionId()).getStatus());
        Mockito.verify(genAiClient, Mockito.never()).answer(ArgumentMatchers.anyString(),
                ArgumentMatchers.anyList(), ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any());
    }

    @Test
    void whenTheAiIsDown_theActionReportsFailed_notCompleted() {
        // ActionStatus.failed had no producer until today (BACKLOG.md item 4), so a genuine
        // execution failure either threw a 500 or reported `completed`.
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenThrow(GenAiUnavailableException.unreachable());

        ActionRequest request = approveSummary(document.getId());
        actionService.processAction(request, owner.getId());

        // Accepted instantly, failed in the background — V22. The row is the record.
        ActionAudit outcome = outcomeOf(request.actionId());
        assertEquals(ActionStatus.failed, outcome.getStatus());
        assertNull(outcome.getResult(), "a failure stores no result");
    }

    @Test
    void insufficientContextIsAFailure_notAnEmptySummary() {
        // A document with no chunks, or nothing clearing the relevance floor. Returning an
        // empty string would render as a blank card that looks like success.
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenReturn(new GenAiAnswerResponse("insufficient_context", "", List.of(), List.of(), null));

        ActionRequest request = approveSummary(document.getId());
        actionService.processAction(request, owner.getId());

        // Accepted instantly, failed in the background — V22. The row is the record.
        assertEquals(ActionStatus.failed, outcomeOf(request.actionId()).getStatus());
    }

    @Test
    void aFailedSummaryCarriesAReasonTheUserCanRead() {
        // THE REPORTED BUG, from the server's half. The user approved a summarize-document
        // proposal, execution failed, and the card said "Action rejected." — the one thing
        // that had definitively not happened, while the audit row recorded `approved`.
        //
        // The status was already `failed`; it carried no reason, so the UI had nothing to
        // show and fell through to its rejected branch. The reason now travels with it.
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenReturn(new GenAiAnswerResponse("insufficient_context", "", List.of(),
                        List.of(), null));

        ActionRequest request = approveSummary(document.getId());
        actionService.processAction(request, owner.getId());

        ActionAudit outcome = outcomeOf(request.actionId());
        assertEquals(ActionStatus.failed, outcome.getStatus());
        assertNotNull(outcome.getFailureReason(), "a failure the user sees must say why");
        assertTrue(outcome.getFailureReason().contains("summarised"),
                "the reason must name what went wrong, not merely that something did");
    }

    @Test
    void aRejectedActionCarriesNoReason() {
        // A rejection has no reason beyond the user's own, and inventing one would be wrong.
        ActionRequest rejected = new ActionRequest("act-" + UUID.randomUUID(), session.getId(),
                ActionDecision.rejected, ActionType.SUMMARIZE_DOCUMENT,
                new SummarizePayload(document.getId(), "report.txt"));

        ActionResult result = actionService.processAction(rejected, owner.getId());

        assertEquals(ActionStatus.rejected, result.status());
        assertNull(result.failureReason());
    }
}
