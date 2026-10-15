package com.bluestone.knowledge_assistant.chat;

import com.bluestone.knowledge_assistant.document.Document;
import com.bluestone.knowledge_assistant.genai.GenAiClient;
import com.bluestone.knowledge_assistant.genai.dto.GenAiAnswerResponse;
import com.bluestone.knowledge_assistant.genai.dto.GenAiCitation;
import com.bluestone.knowledge_assistant.genai.dto.GenAiTurn;
import com.bluestone.knowledge_assistant.support.TestFixtures;
import com.bluestone.knowledge_assistant.user.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.mockito.ArgumentCaptor;
import org.mockito.ArgumentMatchers;
import org.mockito.Mockito;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

import java.util.List;
import java.util.UUID;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class ChatIntegrationTest {

    /**
     * The GenAI service is MOCKED, deliberately and permanently.
     *
     * <p>Without this, these tests pass only while a Python process happens to be listening
     * on port 8000 — and worse, they pass SILENTLY that way. That is how this test suite
     * behaved for exactly one run on Day 8: `sendMessage_returns201` went green by calling a
     * live language model, taking real seconds and real CPU to assert a JSON field.
     *
     * <p>A Spring test asserting Spring's behaviour must not depend on another runtime being
     * up. What Spring owns here is the transaction split, the allow-list it computes, the
     * citation hydration, and the failure mapping — all of which are testable against a stub.
     * What the model actually says is measured in genai-service/benchmarks, not here.
     */
    @MockitoBean private GenAiClient genAiClient;

    @Autowired private MockMvc mockMvc;
    @Autowired private TestFixtures fixtures;

    private User owner;
    private ChatSession session;

    @BeforeEach
    void setUp() {
        owner = fixtures.user();
        session = fixtures.session(owner, "Airport Operations Review");
        fixtures.message(session, "Can you summarize the airport flight schedule?", MessageSender.user);

        // A default grounded answer with no citations, so tests that are about proposals,
        // ownership or status codes do not each have to restate what the AI said. Tests that
        // care about the answer override it with stubAnswer(...).
        stubAnswer("grounded", "A grounded answer.", List.of());
    }

    private RequestPostProcessor asOwner() { return fixtures.as(owner); }

    @Test
    void getSessions_returns200() throws Exception {
        mockMvc.perform(get("/api/chat/sessions").with(asOwner()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[?(@.title == 'Airport Operations Review')]").exists());
    }

    @Test
    void getMessages_returns200_withSeededMessages() throws Exception {
        mockMvc.perform(get("/api/chat/" + session.getId() + "/messages").with(asOwner()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.content == 'Can you summarize the airport flight schedule?')]").exists());
    }

    @Test
    void getMessages_returns404_whenSessionNotFound() throws Exception {
        mockMvc.perform(get("/api/chat/00000000-0000-0000-0000-000000000000/messages").with(asOwner()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("CHAT_NOT_FOUND"));
    }

    @Test
    void sendMessage_returns201_withAssistantResponse() throws Exception {
        String body = "{\"sessionId\":\"" + session.getId() + "\",\"content\":\"Test message\"}";

        mockMvc.perform(post("/api/chat/message")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.sender").value("assistant"));
    }

    @Test
    void sendMessage_hydratesCitationTextFromSpringsOwnDatabase() throws Exception {
        // The service returns a chunk_id and NO text — Spring wrote these rows and reads
        // the excerpt back itself rather than trusting a service to echo it.
        Document document = fixtures.document(owner, "owned-report.txt");
        UUID chunkId = fixtures.documentChunk(
                document, 1,
                // A chunk is long. Real ones average 1,538 characters and reach 2,597.
                "Maintenance overview for the quarter. Runway inspections are completed "
                        + "every quarter. Further notes follow this sentence and are not "
                        + "what the answer rested on.",
                "Maintenance");

        stubAnswer("grounded", "Quarterly.", List.of(new GenAiCitation(chunkId, document.getId(), 0.81,
                        "Runway inspections are completed every quarter.")));

        String body = "{\"sessionId\":\"" + session.getId() + "\",\"content\":\"What does the report say?\"}";

        mockMvc.perform(post("/api/chat/message")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.citations[0].documentName").value("owned-report.txt"))
                // The SENTENCE the answer rested on, not the whole chunk.
                .andExpect(jsonPath("$.citations[0].excerpt")
                        .value("Runway inspections are completed every quarter."))
                .andExpect(jsonPath("$.citations[0].section").value("Maintenance"))
                // A word, never a percentage: 0.81 is above the measured 0.70 band.
                .andExpect(jsonPath("$.citations[0].matchQuality").value("Close match"));
    }

    @Test
    void insufficientContext_becomesASentence_notAnEmptyBubble() throws Exception {
        // The service returns outcome=insufficient_context with an EMPTY answer on purpose:
        // whether there is enough context is decided in code from retrieval scores before the
        // model is called. Turning that into something readable is Spring's job.
        stubAnswer("insufficient_context", "", List.of());

        String body = "{\"sessionId\":\"" + session.getId() + "\",\"content\":\"capital of France?\"}";

        mockMvc.perform(post("/api/chat/message")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.content").value(org.hamcrest.Matchers.containsString(
                        "couldn't find anything in your documents")))
                .andExpect(jsonPath("$.citations").isEmpty());
    }

    @Test
    void anUncitedAnswerWritesNoCitations() throws Exception {
        // Day 7 measured citations resolving roughly 1 in 3: the model paraphrases instead
        // of quoting, and an unresolvable quote is dropped rather than guessed at. Empty is
        // a normal state. An uncited answer is honest; a wrongly cited one is not.
        fixtures.document(owner, "owned-report.txt");
        stubAnswer("grounded", "Some answer with no resolvable quote.", List.of());

        String body = "{\"sessionId\":\"" + session.getId() + "\",\"content\":\"anything\"}";

        mockMvc.perform(post("/api/chat/message")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.content").value("Some answer with no resolvable quote."))
                .andExpect(jsonPath("$.citations").isEmpty());
    }

    @Test
    void whenTheAiIsDown_theChatReturns503_andNotAStackTrace() throws Exception {
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenThrow(com.bluestone.knowledge_assistant.genai.GenAiUnavailableException.unreachable());

        String body = "{\"sessionId\":\"" + session.getId() + "\",\"content\":\"anything\"}";

        mockMvc.perform(post("/api/chat/message")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("AI_UNAVAILABLE"));
    }

    @Test
    void historyIsSent_andExcludesTheQuestionBeingAsked() throws Exception {
        // The session fixture already contains one earlier user message.
        String body = "{\"sessionId\":\"" + session.getId() + "\",\"content\":\"tell me in detail\"}";

        mockMvc.perform(post("/api/chat/message")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated());

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<GenAiTurn>> history = ArgumentCaptor.forClass(List.class);
        Mockito.verify(genAiClient).answer(ArgumentMatchers.eq("tell me in detail"),
                ArgumentMatchers.anyList(), ArgumentMatchers.any(), history.capture(), ArgumentMatchers.any());

        List<String> sent = history.getValue().stream().map(GenAiTurn::content).toList();

        // The earlier turn is there...
        org.junit.jupiter.api.Assertions.assertTrue(
                sent.contains("Can you summarize the airport flight schedule?"),
                "the previous user turn is what makes a follow-up resolvable");

        // ...and the question being asked is NOT. It was persisted moments earlier by phase
        // one, so an unfiltered query would put the same sentence in the prompt twice.
        org.junit.jupiter.api.Assertions.assertFalse(sent.contains("tell me in detail"),
                "the current question must not be sent back as its own context");
    }

    @Test
    void theFirstTurnOfAConversationSendsEmptyHistory() throws Exception {
        String body = "{\"initialMessage\":\"what are the formulas of adbms\"}";

        mockMvc.perform(post("/api/chat/sessions")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated());

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<GenAiTurn>> history = ArgumentCaptor.forClass(List.class);
        Mockito.verify(genAiClient).answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                ArgumentMatchers.any(), history.capture(), ArgumentMatchers.any());

        // Empty, not null, and not a 422: a first turn genuinely has no history, which is a
        // normal state rather than a caller defect. That is why `history` has a default and
        // `allowed_document_ids` deliberately does not.
        org.junit.jupiter.api.Assertions.assertTrue(history.getValue().isEmpty());
    }

    @Test
    void anUnsupportedRequestExplainsTheLimitation_notTheDocuments() throws Exception {
        // Telling someone their documents do not cover "send an email" is a FALSE
        // explanation: the documents are not the reason, and it invites them to rephrase or
        // upload something, which cannot help. Day 12's done-when is "explains limitations
        // clearly", and a clear explanation names the limitation.
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenReturn(new GenAiAnswerResponse("insufficient_context", "", List.of(), List.of(),
                        new com.bluestone.knowledge_assistant.genai.dto.GenAiTrace(
                                "t", 0, 0, "qa-v2", 0, 0, 0, 0, List.of(), "send messages",
                                null, null, List.of())));

        String body = "{\"sessionId\":\"" + session.getId() + "\",\"content\":\"send an email\"}";

        mockMvc.perform(post("/api/chat/message")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.content").value(org.hamcrest.Matchers.containsString("cannot send messages")))
                .andExpect(jsonPath("$.content").value(
                        org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("couldn't find anything"))));
    }

    @Test
    void a503FromTheAiReportsTheREALreason_notAGuess() throws Exception {
        // This answered "the AI is still starting up" for every 503 — true on Day 8, when a
        // model loading at boot was the only cause. Day 13 added a cloud model running out of
        // daily quota, which looks identical on the wire and means the opposite: waiting is
        // the one thing that cannot help, because the free-tier cap is per day and per model.
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenThrow(com.bluestone.knowledge_assistant.genai.GenAiUnavailableException.because(
                        "The cloud model 'gemini-3.6-flash' has used up its daily free quota."));

        String body = "{\"sessionId\":\"" + session.getId() + "\",\"content\":\"anything\"}";

        mockMvc.perform(post("/api/chat/message")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.message").value(
                        org.hamcrest.Matchers.containsString("daily free quota")))
                .andExpect(jsonPath("$.message").value(
                        org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("starting up"))));
    }

    private void stubAnswer(String outcome, String answer, List<GenAiCitation> citations) {
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenReturn(new GenAiAnswerResponse(outcome, answer, citations, List.of(), null));
    }

    @Test
    void createSession_surfacesAProposal_onTheVeryFirstMessage() throws Exception {
        // The reported bug this guards: opening a chat produced no proposal and only the
        // SECOND identical message did, because "new chat" ran a separate copy of the reply
        // logic that lacked the proposal branch.
        //
        // Day 14b changed where the proposal COMES FROM — the GenAI service decides, Spring
        // translates — so the stub now supplies one. The bug being guarded is unchanged: the
        // create path and the send path must handle a proposal identically.
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenReturn(new GenAiAnswerResponse("grounded", "An answer.", List.of(),
                        List.of(new com.bluestone.knowledge_assistant.genai.dto.GenAiProposal(
                                java.util.Map.of("tool", "create-task",
                                        "title", "Follow up on the runway inspection",
                                        "priority", "medium"),
                                "Create a task: Follow up on the runway inspection")),
                        null));

        mockMvc.perform(post("/api/chat/sessions")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"initialMessage\":\"Please follow up on the runway inspection\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.initialResponse.actions[0].type").value("create-task"))
                .andExpect(jsonPath("$.initialResponse.actions[0].payload.title")
                        .value("Follow up on the runway inspection"));
    }

    @Test
    void createSession_proposesNothing_whenTheServiceProposedNothing() throws Exception {
        mockMvc.perform(post("/api/chat/sessions")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"initialMessage\":\"Good morning\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.initialResponse.actions").doesNotExist());
    }

    @Test
    void sendMessage_citesNothing_whenTheCallerHasNoDocuments() throws Exception {
        String body = "{\"sessionId\":\"" + session.getId() + "\",\"content\":\"Anything?\"}";

        mockMvc.perform(post("/api/chat/message")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.citations").isEmpty());
    }

    // --- a near miss is not a missing document (M3 D19) ----------------------
    //
    // Reported from real use: "tell me about ai saftey" answered "I couldn't find anything
    // in your documents… upload a document that covers it" while AI_safety.pdf sat in the
    // corpus with 81 chunks. The misspelling scores 0.5355 against a 0.60 floor; the correct
    // spelling scores 0.7120. One letter, and the advice pointed at the wrong problem.

    private GenAiAnswerResponse nothingRetrieved(Double bestRejected, Double floor) {
        return new GenAiAnswerResponse("insufficient_context", "", List.of(), List.of(),
                new com.bluestone.knowledge_assistant.genai.dto.GenAiTrace(
                        "t", 0, 0, "qa-v2", 0, 0, 0, 0, List.of(), null, bestRejected, floor,
                        List.of()));
    }

    private String replyFor(GenAiAnswerResponse stubbed) throws Exception {
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenReturn(stubbed);
        String body = "{\"sessionId\":\"" + session.getId() + "\",\"content\":\"tell me about ai saftey\"}";
        return mockMvc.perform(post("/api/chat/message").with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
    }

    @Test
    void aNearMissBlamesTheWordingRatherThanTheDocuments() throws Exception {
        String reply = replyFor(nothingRetrieved(0.5355, 0.60));

        // The old advice was actively wrong here — there was nothing to upload.
        org.assertj.core.api.Assertions.assertThat(reply)
                .contains("typo")
                .doesNotContain("upload a document");
    }

    @Test
    void aGenuineMissStillSuggestsUploadingSomething() throws Exception {
        // Far below the floor: the documents really do not cover it, and the original
        // advice is the right advice. Collapsing the two cases is what caused the report.
        String reply = replyFor(nothingRetrieved(0.21, 0.60));

        org.assertj.core.api.Assertions.assertThat(reply)
                .contains("upload a document")
                .doesNotContain("typo");
    }

    @Test
    void aQueryThatMatchedNothingAtAllIsTreatedAsAGenuineMiss() throws Exception {
        // Null means there was nothing to be near — different from being near a miss.
        String reply = replyFor(nothingRetrieved(null, null));

        org.assertj.core.api.Assertions.assertThat(reply).contains("upload a document");
    }

    @Test
    void aCorrectedSpellingIsReportedToTheUser() throws Exception {
        // ANSWERING A DIFFERENT QUESTION WITHOUT SAYING SO IS A SUBSTITUTION, not a
        // convenience. The user typed "saftey"; retrieval searched "safety". They are
        // entitled to know that before they trust the answer.
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenReturn(new GenAiAnswerResponse("grounded", "AI safety is about alignment.",
                        List.of(), List.of(),
                        new com.bluestone.knowledge_assistant.genai.dto.GenAiTrace(
                                "t", 7, 0, "qa-v2", 10, 10, 10, 10, List.of(), null, null, 0.60,
                                List.of(new com.bluestone.knowledge_assistant.genai.dto.GenAiTrace
                                        .SpellingCorrection("saftey", "safety")))));

        String body = "{\"sessionId\":\"" + session.getId() + "\",\"content\":\"tell me about ai saftey\"}";

        mockMvc.perform(post("/api/chat/message").with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.corrections.length()").value(1))
                .andExpect(jsonPath("$.corrections[0].typed").value("saftey"))
                .andExpect(jsonPath("$.corrections[0].used").value("safety"));
    }

    @Test
    void anOrdinaryAnswerCarriesNoCorrections() throws Exception {
        // Empty on almost every message. A field that is always populated would be noise,
        // and the UI decides to render nothing from exactly this.
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenReturn(new GenAiAnswerResponse("grounded", "An answer.", List.of(), List.of(),
                        new com.bluestone.knowledge_assistant.genai.dto.GenAiTrace(
                                "t", 7, 0, "qa-v2", 10, 10, 10, 10, List.of(), null, null, 0.60,
                                List.of())));

        String body = "{\"sessionId\":\"" + session.getId() + "\",\"content\":\"tell me about ai safety\"}";

        mockMvc.perform(post("/api/chat/message").with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.corrections").isEmpty());
    }
}
