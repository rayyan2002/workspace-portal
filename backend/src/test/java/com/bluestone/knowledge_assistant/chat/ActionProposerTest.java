package com.bluestone.knowledge_assistant.chat;

import com.bluestone.knowledge_assistant.chat.dto.ActionProposalDto;
import com.bluestone.knowledge_assistant.chat.dto.MessageRequest;
import com.bluestone.knowledge_assistant.document.Document;
import com.bluestone.knowledge_assistant.document.DocumentStatus;
import com.bluestone.knowledge_assistant.genai.GenAiClient;
import com.bluestone.knowledge_assistant.genai.dto.GenAiAnswerResponse;
import com.bluestone.knowledge_assistant.genai.dto.GenAiProposal;
import com.bluestone.knowledge_assistant.support.TestFixtures;
import com.bluestone.knowledge_assistant.user.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentMatchers;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Day 14b: what Spring does with a proposal — which is TRANSLATE it, not decide it.
 *
 * <p><strong>This file used to test routing and no longer does, because Spring no longer
 * routes.</strong> The keyword trigger list it exercised has moved to
 * {@code genai-service/app/intent.py}, the only side of the system holding a sentence
 * encoder and therefore the only side that can run a classifier instead of matching strings
 * somebody thought of in advance. Routing ACCURACY is measured there, against the same
 * held-out set in {@code evaluation/tool_cases.json} that this file used to read:
 *
 * <pre>  .venv/bin/python -m pytest tests/test_intent.py -m routing -q</pre>
 *
 * <p>Measured at the move: keywords alone 25/27, classifier alone 24/27, the two together
 * 26/27, all with zero false positives. The rules were relocated rather than replaced —
 * they are still the better half for create-task — and the one language that owns them now
 * owns all of them.
 *
 * <p>What is tested HERE is the half that genuinely belongs to Spring: turning a
 * {@code document_id} into a filename, re-checking that the caller may see it, and refusing
 * anything that cannot be made safe. None of that could have lived in Python, which holds
 * SELECT on the chunk tables and does not own {@code documents}.
 */
@SpringBootTest
@ActiveProfiles("test")
@Transactional
class ActionProposerTest {

    @MockitoBean private GenAiClient genAiClient;
    @Autowired private ChatSessionService chatSessionService;
    @Autowired private ActionProposer actionProposer;
    @Autowired private TestFixtures fixtures;

    private User owner;
    private ChatSession session;

    @BeforeEach
    void setUp() {
        owner = fixtures.user();
        session = fixtures.session(owner, "Proposals");
        stub(List.of());
    }

    private void stub(List<GenAiProposal> proposals) {
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenReturn(new GenAiAnswerResponse("grounded", "An answer.", List.of(), proposals, null));
    }

    private List<ActionProposalDto> turnWith(List<GenAiProposal> proposals) {
        stub(proposals);
        return chatSessionService.sendMessage(
                new MessageRequest(session.getId(), "anything at all", null), owner.getId()).actions();
    }

    private static GenAiProposal proposal(String label, Map<String, Object> arguments) {
        return new GenAiProposal(arguments, label);
    }

    private static Map<String, Object> args(Object... pairs) {
        // HashMap, not Map.of: several cases below deliberately put a NULL value in, which
        // Map.of rejects, and a null argument is exactly the malformed input under test.
        Map<String, Object> map = new HashMap<>();
        for (int i = 0; i < pairs.length; i += 2) {
            map.put((String) pairs[i], pairs[i + 1]);
        }
        return map;
    }

    // --- Spring must not route ----------------------------------------------

    @Test
    void springProposesNothingOfItsOwnAccord() {
        // THE REGRESSION GUARD FOR THE WHOLE MOVE. Every one of these used to produce a
        // proposal from a keyword list in ChatSessionService. If someone re-adds one, this
        // fails — a second router in a second language is the drift this day existed to end.
        for (String message : List.of("create a task to review the runway inspection findings",
                "remind me to follow up on the finance report",
                "add a task for the demo rehearsal",
                "track this: the LSTM inference time looks wrong")) {
            stub(List.of());
            assertNull(chatSessionService.sendMessage(
                            new MessageRequest(session.getId(), message, null), owner.getId()).actions(),
                    "Spring routed \"" + message + "\" on its own — routing belongs to app.intent");
        }
    }

    @Test
    void noProposalsMeansAbsentRatherThanEmpty() {
        // The published contract makes MessageDto.actions optional and the frontend's
        // ActionProposal[] optional with it. An empty array would render an empty container.
        assertNull(turnWith(List.of()));
        assertNull(actionProposer.translate(null, owner.getId()));
    }

    // --- create-task --------------------------------------------------------

    @Test
    void aCreateTaskProposalIsTranslatedFieldByField() {
        List<ActionProposalDto> proposals = turnWith(List.of(proposal(
                "Create a task: Review the runway inspection findings",
                args("tool", "create-task", "title", "Review the runway inspection findings",
                        "priority", "medium"))));

        assertNotNull(proposals);
        assertEquals("create-task", proposals.get(0).type());
        assertEquals("Review the runway inspection findings", proposals.get(0).payload().get("title"));
        assertEquals("medium", proposals.get(0).payload().get("priority"));
        assertTrue(proposals.get(0).id().startsWith("act-"),
                "Spring mints the id because Spring owns the action_audit row it becomes");
    }

    @Test
    void theLabelComesFromTheServiceRatherThanAConstant() {
        // Every proposal used to read "Create a tracking task for this request".
        List<ActionProposalDto> proposals = turnWith(List.of(proposal(
                "Create a task: Follow up on the finance report",
                args("tool", "create-task", "title", "Follow up on the finance report",
                        "priority", "medium"))));

        assertTrue(proposals.get(0).label().contains("finance report"), proposals.get(0).label());
    }

    @Test
    void aMissingLabelStillLeavesSomethingOnTheApproveButton() {
        List<ActionProposalDto> proposals = turnWith(List.of(proposal(
                "   ", args("tool", "create-task", "title", "Renew the certificate",
                        "priority", "low"))));

        assertEquals("Create a task: Renew the certificate", proposals.get(0).label());
    }

    @Test
    void anUnknownPriorityIsDroppedRatherThanDefaulted() {
        // "urgent" is not a TaskPriority. Guessing which of low/medium/high it meant would
        // put a value in front of a human that nothing in the system actually chose.
        assertNull(turnWith(List.of(proposal("x",
                args("tool", "create-task", "title", "t", "priority", "urgent")))));
    }

    @Test
    void anOverLongTitleIsDroppedRatherThanTruncated() {
        // Truncating would show the user a different task from the one that gets stored,
        // and they would be approving the one on screen.
        assertNull(turnWith(List.of(proposal("x",
                args("tool", "create-task", "title", "x".repeat(256), "priority", "medium")))));
    }

    @Test
    void aTitleThatIsMissingOrBlankIsDropped() {
        assertNull(turnWith(List.of(proposal("x", args("tool", "create-task", "priority", "medium")))));
        assertNull(turnWith(List.of(proposal("x",
                args("tool", "create-task", "title", "   ", "priority", "medium")))));
    }

    // --- summarize-document: the gap this day closed ------------------------

    @Test
    void aSummarizeProposalGetsTheFilenameSpringAlreadyHolds() {
        // THE TRANSLATION THE CONTRACT SPECIFIED AND NOTHING PERFORMED.
        // INTEGRATION_CONTRACT.md §5 has said since Day 10 that the model quotes a sentence,
        // the service resolves it to a chunk, and SPRING maps that to the document row it
        // wrote. SummarizePayload needs {documentId, documentName}; the published tool
        // schema carries a chunk_ordinal; for five days no code bridged the two.
        Document document = fixtures.document(owner, "runway-inspection.pdf", DocumentStatus.ready);

        List<ActionProposalDto> proposals = turnWith(List.of(proposal("Summarise this document",
                args("tool", "summarize-document", "chunk_ordinal", 1,
                        "document_id", document.getId().toString()))));

        assertNotNull(proposals, "a summarize proposal naming a readable document must survive");
        assertEquals("summarize-document", proposals.get(0).type());
        assertEquals(document.getId().toString(), proposals.get(0).payload().get("documentId"));
        assertEquals("runway-inspection.pdf", proposals.get(0).payload().get("documentName"));
    }

    @Test
    void aSummarizeProposalNamingSomeoneElsesDocumentIsDropped() {
        // THE REASON OWNERSHIP IS RE-CHECKED HERE. The id crossed a network boundary, so it
        // is a claim. Without this check the service could name any row in the table and
        // Spring would put its filename on screen.
        User stranger = fixtures.user();
        Document theirs = fixtures.document(stranger, "private-salaries.xlsx", DocumentStatus.ready);

        assertNull(turnWith(List.of(proposal("Summarise this document",
                args("tool", "summarize-document", "chunk_ordinal", 1,
                        "document_id", theirs.getId().toString())))));
    }

    @Test
    void aSummarizeProposalForADocumentThatIsNotReadyIsDropped() {
        // Same rule that builds allowed_document_ids: owned AND ready. A proposal can only
        // ever name a document the user could already have asked about.
        Document pending = fixtures.document(owner, "still-uploading.pdf", DocumentStatus.processing);

        assertNull(turnWith(List.of(proposal("Summarise this document",
                args("tool", "summarize-document", "chunk_ordinal", 1,
                        "document_id", pending.getId().toString())))));
    }

    @Test
    void aSummarizeProposalWithNoResolvedDocumentIsDropped() {
        // The service resolves chunk_ordinal to a document_id in code and drops the proposal
        // when it cannot. A null arriving here means an ordinal that resolved to nothing.
        assertNull(turnWith(List.of(proposal("Summarise this document",
                args("tool", "summarize-document", "chunk_ordinal", 1, "document_id", null)))));
    }

    @Test
    void aMalformedDocumentIdIsDroppedRatherThanThrown() {
        assertNull(turnWith(List.of(proposal("Summarise this document",
                args("tool", "summarize-document", "chunk_ordinal", 1,
                        "document_id", "not-a-uuid")))));
    }

    // --- lookup-knowledge ---------------------------------------------------

    @Test
    void aLookupProposalIsTranslated() {
        List<ActionProposalDto> proposals = turnWith(List.of(proposal(
                "Search your documents for: retention policy",
                args("tool", "lookup-knowledge", "query", "retention policy"))));

        assertNotNull(proposals);
        assertEquals("lookup-knowledge", proposals.get(0).type());
        assertEquals("retention policy", proposals.get(0).payload().get("query"));
    }

    @Test
    void anOverLongQueryIsDropped() {
        assertNull(turnWith(List.of(proposal("x",
                args("tool", "lookup-knowledge", "query", "x".repeat(501))))));
    }

    // --- failing closed ------------------------------------------------------

    @Test
    void anUnknownToolIsNeverRoundedToAKnownOne() {
        // "delete-everything" is not a typo for "create-task", and nothing here guesses
        // what the service meant.
        assertNull(turnWith(List.of(proposal("Delete everything",
                args("tool", "delete-everything", "title", "x", "priority", "high")))));
    }

    @Test
    void underscoresAreRejectedBecauseTheRunningSystemUsesHyphens() {
        // These literals go to Postgres (action_audit.type), to Jackson's deserialisation
        // and to the frontend's discriminated union. The training tracker writes them with
        // underscores; the running system does not, and the running system wins.
        assertNull(turnWith(List.of(proposal("x",
                args("tool", "create_task", "title", "t", "priority", "medium")))));
    }

    @Test
    void aProposalWithNoArgumentsAtAllIsDropped() {
        assertNull(turnWith(List.of(new GenAiProposal(null, "Looks official"))));
        assertNull(turnWith(List.of(proposal("x", args()))));
    }

    @Test
    void oneBadProposalDoesNotCostTheOtherOneOrTheAnswer() {
        // WHY GenAiProposal.arguments IS AN UNTYPED MAP. A Jackson polymorphic union would
        // have thrown while deserialising the whole response, so one unrecognised proposal
        // would cost the user their ANSWER. A proposal is a suggestion; the answer is the
        // product. Failing closed has to happen at the right granularity.
        List<ActionProposalDto> proposals = turnWith(List.of(
                proposal("bad", args("tool", "delete-everything")),
                proposal("good", args("tool", "create-task", "title", "Survivor",
                        "priority", "high"))));

        assertNotNull(proposals);
        assertEquals(1, proposals.size());
        assertEquals("Survivor", proposals.get(0).payload().get("title"));
    }

    @Test
    void theServicesArgumentMapNeverReachesTheBrowser() {
        // Every field the UI sees is one the translator rebuilt. An extra key invented on
        // the Python side cannot ride along into the payload the frontend narrows on.
        List<ActionProposalDto> proposals = turnWith(List.of(proposal("x",
                args("tool", "create-task", "title", "Clean", "priority", "low",
                        "smuggled", "should not appear"))));

        assertEquals(Map.of("title", "Clean", "priority", "low"), proposals.get(0).payload());
    }

    // --- the boundary the governance flow rests on ---------------------------

    @Test
    void proposingStillWritesNothing() {
        turnWith(List.of(proposal("Create a task: Review the findings",
                args("tool", "create-task", "title", "Review the findings", "priority", "medium"))));

        assertEquals(0, fixtures.taskCount(owner), "proposing must not create a task");
    }

    @Test
    void translationNeedsNoSessionAndSoCannotWriteAnAuditRow() {
        // Called directly, outside a turn: the translator reads documents and nothing else.
        List<ActionProposalDto> proposals = actionProposer.translate(
                List.of(proposal("x", args("tool", "lookup-knowledge", "query", "q"))),
                owner.getId());

        assertEquals(1, proposals.size());
        assertEquals(0, fixtures.taskCount(owner));
    }
}
