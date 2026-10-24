package com.knowledgeassistant.document;

import com.knowledgeassistant.chat.MessageSender;
import com.knowledgeassistant.support.TestFixtures;
import com.knowledgeassistant.user.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.knowledgeassistant.genai.GenAiClient;
import com.knowledgeassistant.genai.GenAiUnavailableException;
import com.knowledgeassistant.genai.dto.GenAiChunk;
import com.knowledgeassistant.genai.dto.GenAiIngestResponse;
import com.knowledgeassistant.genai.dto.GenAiIngestTrace;
import org.mockito.ArgumentMatchers;
import org.mockito.Mockito;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class DocumentIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private TestFixtures fixtures;

    private User owner;

    @BeforeEach
    void setUp() {
        owner = fixtures.user();
        fixtures.document(owner, "maintenance_log_Q2.md");
    }

    private org.springframework.test.web.servlet.request.RequestPostProcessor userA() {
        return fixtures.as(owner);
    }


    @Test
    void getDocuments_returns200_withSeededDocuments() throws Exception {
        mockMvc.perform(get("/api/documents").with(userA()))
                .andExpect(status().isOk())
                // Assert the specific seeded document exists rather than an exact array length
                .andExpect(jsonPath("$.items[?(@.filename == 'maintenance_log_Q2.md')]").exists());
    }

    @Test
    void getDocumentById_returns404_whenNotFound() throws Exception {
        mockMvc.perform(get("/api/documents/00000000-0000-0000-0000-000000000000").with(userA()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("DOCUMENT_NOT_FOUND"));
    }

    @Test
    void upload_returns400_forAnUnsupportedFileType() throws Exception {
        // Every rejection path used to return 500: DocumentValidationException did not
        // extend DomainException, so the global handler never mapped it. The suite
        // missed it because it only ever uploaded a valid file.
        MockMultipartFile blocked = new MockMultipartFile(
                "file", "malware.exe", "application/octet-stream", "MZ".getBytes());

        mockMvc.perform(multipart("/api/documents/upload").file(blocked).with(userA()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FILE_TYPE"));
    }

    @Test
    void upload_returns400_whenNoFileIsProvided() throws Exception {
        mockMvc.perform(multipart("/api/documents/upload").with(userA()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MISSING_FILE"));
    }

    /**
     * Day 16: the GenAI service is MOCKED here, and that is not optional.
     *
     * <p>Before this mock existed, wiring ingestion into upload made this test pass by
     * making a real HTTP call to a Python process that happened to be running on this
     * machine. It went green for the wrong reason, and would have gone red on any machine
     * where the service was not up. "A Spring test that depends on a Python process being
     * alive" is the trap Day 8 named and this is the first test that could fall into it.
     */
    @MockitoBean
    private GenAiClient genAiClient;

    private void stubIngest(int chunks) {
        List<GenAiChunk> body = new ArrayList<>();
        for (int i = 1; i <= chunks; i++) {
            body.add(new GenAiChunk(i, "chunk " + i, 3, 0, 7, "Intro", 1,
                    Collections.nCopies(384, 0.05)));
        }
        Mockito.when(genAiClient.ingest(ArgumentMatchers.any(), ArgumentMatchers.anyString(),
                        ArgumentMatchers.anyString(), ArgumentMatchers.any()))
                .thenReturn(new GenAiIngestResponse(UUID.randomUUID(), chunks,
                        "BAAI/bge-small-en-v1.5", "5c38ec7c", "semantic", 384, body,
                        new GenAiIngestTrace("t", 1, 1, 1, 3)));
    }

    @Test
    void upload_returns201_andTheDocumentIsSearchable() throws Exception {
        // READY, and for the first time that word is earned.
        //
        // `ready` meant listable/previewable/downloadable until Day 6, when retrieval began
        // building allowed_document_ids from it and the word quietly acquired a second
        // meaning: SEARCHABLE. An unchunked upload did not satisfy it, so uploads stopped at
        // `processing` and stayed there — Day 16 is what advances them.
        stubIngest(3);
        MockMultipartFile file = new MockMultipartFile(
                "file", "test.txt", "text/plain", "hello world".getBytes());

        mockMvc.perform(multipart("/api/documents/upload").file(file).with(userA()))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.filename").value("test.txt"))
                .andExpect(jsonPath("$.status").value("ready"));
    }

    @Test
    void upload_leavesTheDocumentFailed_whenTheServiceCannotProcessIt() throws Exception {
        // THE FIRST TIME `failed` HAS EVER BEEN PRODUCED. BACKLOG.md item 5 recorded it as a
        // value in an enum that nothing could emit.
        //
        // The upload itself SUCCEEDED — bytes stored, row committed — so this is still a
        // 201. A 5xx would be a lie about the upload and would leave the user with no
        // document at all; `failed` is a document they can see and re-upload.
        Mockito.when(genAiClient.ingest(ArgumentMatchers.any(), ArgumentMatchers.anyString(),
                        ArgumentMatchers.anyString(), ArgumentMatchers.any()))
                .thenThrow(GenAiUnavailableException.because(
                        "No readable text could be extracted. A scanned PDF needs OCR."));
        MockMultipartFile file = new MockMultipartFile(
                "file", "scan.pdf", "application/pdf", "%PDF-1.4 no text layer".getBytes());

        mockMvc.perform(multipart("/api/documents/upload").file(file).with(userA()))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("failed"));
    }

    @Test
    void upload_leavesTheDocumentFailed_whenTheServiceReturnsNoChunks() throws Exception {
        // A document with zero chunks must never be `ready`. It would enter
        // allowed_document_ids, be sent to the AI service on every question, and contribute
        // nothing to any answer — with no error anywhere. That is the exact failure the
        // `processing` status was introduced to stop, and it must not return via ingestion.
        stubIngest(0);
        MockMultipartFile file = new MockMultipartFile(
                "file", "empty.txt", "text/plain", "   ".getBytes());

        mockMvc.perform(multipart("/api/documents/upload").file(file).with(userA()))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("failed"));
    }

    // --- deleting a document that conversations cite (M3 D19) ----------------
    //
    // `citations.document_id` is ON DELETE RESTRICT, so the delete used to fail on the
    // constraint and the browser showed "Failed to delete … The document has been restored."
    // True, and useless: it named no cause, so the document simply looked undeletable.

    @Test
    void deletionImpact_isEmpty_whenNothingCitesTheDocument() throws Exception {
        var doc = fixtures.document(owner, "uncited.txt");

        mockMvc.perform(get("/api/documents/" + doc.getId() + "/deletion-impact").with(userA()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.filename").value("uncited.txt"))
                .andExpect(jsonPath("$.chats").isEmpty());
    }

    @Test
    void deletionImpact_namesEveryConversationThatWouldBeDeleted() throws Exception {
        var doc = fixtures.document(owner, "cited.txt");
        var chat = fixtures.session(owner, "What does the policy say?");
        var question = fixtures.message(chat, "what does it say", MessageSender.user);
        fixtures.message(chat, "it says this", MessageSender.assistant);
        fixtures.citation(question, doc);

        mockMvc.perform(get("/api/documents/" + doc.getId() + "/deletion-impact").with(userA()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.chats.length()").value(1))
                .andExpect(jsonPath("$.chats[0].title").value("What does the policy say?"))
                // Both messages are counted, not just the one holding the citation: the whole
                // conversation is what the user loses.
                .andExpect(jsonPath("$.chats[0].messageCount").value(2));
    }

    @Test
    void deletionImpact_reportsWhenAChatAlsoUsesOtherDocuments() throws Exception {
        // THE CASE THE CONFIRMATION EXISTS FOR. A conversation is not necessarily ABOUT the
        // document being deleted — on the live corpus a ten-message chat titled "tell me about
        // finance" cites four documents. Listing a title alone would hide that.
        var doomed = fixtures.document(owner, "doomed.txt");
        var other = fixtures.document(owner, "unrelated.txt");
        var chat = fixtures.session(owner, "mostly about something else");
        var message = fixtures.message(chat, "a question", MessageSender.user);
        fixtures.citation(message, doomed);
        fixtures.citation(message, other);

        mockMvc.perform(get("/api/documents/" + doomed.getId() + "/deletion-impact").with(userA()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.chats[0].otherDocuments.length()").value(1))
                // NAMED, not counted: the dialog links to it, and the user can go and read it
                // because that document survives the deletion.
                .andExpect(jsonPath("$.chats[0].otherDocuments[0].filename").value("unrelated.txt"))
                .andExpect(jsonPath("$.chats[0].otherDocuments[0].id").value(other.getId().toString()));
    }

    @Test
    void theOtherDocumentsAreNotDeletedWithTheConversation() throws Exception {
        // THE QUESTION THE DIALOG HAS TO ANSWER. Deleting a document destroys the chats that
        // cite it — but NOT the other documents those chats also referenced. Only the
        // discussion of them is lost.
        var doomed = fixtures.document(owner, "doomed.txt");
        var survivor = fixtures.document(owner, "survivor.txt");
        var chat = fixtures.session(owner, "covers both");
        var message = fixtures.message(chat, "a question", MessageSender.user);
        fixtures.citation(message, doomed);
        fixtures.citation(message, survivor);

        mockMvc.perform(delete("/api/documents/" + doomed.getId() + "?deleteLinkedChats=true").with(userA()))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/api/documents/" + doomed.getId()).with(userA()))
                .andExpect(status().isNotFound());
        mockMvc.perform(get("/api/documents/" + survivor.getId()).with(userA()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.filename").value("survivor.txt"));
    }

    @Test
    void delete_returns409_ratherThanAnOpaqueFailure_whenAConversationCitesIt() throws Exception {
        var doc = fixtures.document(owner, "protected.txt");
        var chat = fixtures.session(owner, "a conversation");
        fixtures.citation(fixtures.message(chat, "q", MessageSender.user), doc);

        mockMvc.perform(delete("/api/documents/" + doc.getId()).with(userA()))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("DOCUMENT_IN_USE"))
                // The message must say what is in the way. The old failure said nothing.
                .andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("conversation")));

        mockMvc.perform(get("/api/documents/" + doc.getId()).with(userA()))
                .andExpect(status().isOk());
    }

    @Test
    void delete_withTheFlag_removesTheDocumentAndTheConversationsCitingIt() throws Exception {
        var doc = fixtures.document(owner, "going.txt");
        var chat = fixtures.session(owner, "goes with it");
        fixtures.citation(fixtures.message(chat, "q", MessageSender.user), doc);

        mockMvc.perform(delete("/api/documents/" + doc.getId() + "?deleteLinkedChats=true").with(userA()))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/api/documents/" + doc.getId()).with(userA()))
                .andExpect(status().isNotFound());
        // There is no GET /api/chat/sessions/{id}; the conversation's own messages endpoint is
        // the reachable proof that the session is gone.
        mockMvc.perform(get("/api/chat/" + chat.getId() + "/messages").with(userA()))
                .andExpect(status().isNotFound());
        mockMvc.perform(get("/api/chat/sessions").with(userA()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[?(@.title == 'goes with it')]").doesNotExist());
    }

    @Test
    void delete_stillWorksWithoutTheFlag_whenNothingCitesTheDocument() throws Exception {
        // The regression guard. The flag must not become a requirement for the ordinary case.
        var doc = fixtures.document(owner, "lonely.txt");

        mockMvc.perform(delete("/api/documents/" + doc.getId()).with(userA()))
                .andExpect(status().isNoContent());
    }

    @Test
    void deletionImpact_neverRevealsAnotherUsersConversations() throws Exception {
        // The query is scoped by user_id as well as document. A shared document would
        // otherwise let one user read another's conversation titles.
        var doc = fixtures.document(owner, "shared.txt");
        var stranger = fixtures.user();
        var theirChat = fixtures.session(stranger, "a private conversation");
        fixtures.citation(fixtures.message(theirChat, "q", MessageSender.user), doc);

        mockMvc.perform(get("/api/documents/" + doc.getId() + "/deletion-impact").with(userA()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.chats").isEmpty());
    }
}
