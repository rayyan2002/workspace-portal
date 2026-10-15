package com.knowledgeassistant.auth;

import com.knowledgeassistant.chat.ChatSession;
import com.knowledgeassistant.document.Document;
import com.knowledgeassistant.support.TestFixtures;
import com.knowledgeassistant.task.Task;
import com.knowledgeassistant.user.RoleName;
import com.knowledgeassistant.user.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Authorization boundaries.
 *
 * <p>Two users are built per test rather than borrowed from seed data. With a single
 * user every scoping assertion passes whether or not scoping exists, so user B's owned
 * rows are what make "A cannot see B" a real claim instead of a vacuous one.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class AuthorizationIntegrationTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private TestFixtures fixtures;

    private User userA;
    private User userB;
    private ChatSession sessionA;
    private ChatSession sessionB;
    private Task taskB;
    private Document documentA;
    private Document documentB;

    @BeforeEach
    void setUp() {
        userA = fixtures.user(RoleName.ROLE_USER, RoleName.ROLE_ADMIN);
        userB = fixtures.user(RoleName.ROLE_USER);

        sessionA = fixtures.session(userA, "A's session");
        sessionB = fixtures.session(userB, "B's private session");

        fixtures.task(sessionA, "A's task");
        taskB = fixtures.task(sessionB, "B's private task");

        documentA = fixtures.document(userA, "a-report.txt");
        documentB = fixtures.document(userB, "b-private.txt");

        fixtures.audit(sessionB, "act-b-only");
    }

    private RequestPostProcessor asA() { return fixtures.as(userA); }
    private RequestPostProcessor asB() { return fixtures.as(userB); }

    // --- Authentication: closed by default -----------------------------------

    @Test
    void protectedEndpoint_returns401_withNoToken() throws Exception {
        mockMvc.perform(get("/api/chat/sessions"))
                .andExpect(status().isUnauthorized())
                // Written by the entry point; @RestControllerAdvice never sees it.
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.timestamp").exists())
                .andExpect(jsonPath("$.traceId").exists());
    }

    @Test
    void protectedEndpoint_returns401_withGarbageToken() throws Exception {
        mockMvc.perform(get("/api/tasks").with(fixtures.bearer("not-a-real-jwt")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void protectedEndpoint_returns401_withMalformedHeader() throws Exception {
        mockMvc.perform(get("/api/tasks").header("Authorization", "missing-the-bearer-prefix"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void openEndpointsRemainReachableWithoutToken() throws Exception {
        mockMvc.perform(get("/api/health")).andExpect(status().isOk());
    }

    // --- Roles ----------------------------------------------------------------

    @Test
    void adminEndpoint_returns403_forANonAdmin() throws Exception {
        mockMvc.perform(get("/api/admin/users").with(asB()))
                .andExpect(status().isForbidden())
                // 403, not 404: the caller is known and nothing about anyone's data
                // leaks by admitting the endpoint exists.
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }

    @Test
    void adminEndpoint_returns200_forAnAdmin() throws Exception {
        mockMvc.perform(get("/api/admin/users").with(asA()))
                .andExpect(status().isOk());
    }

    // --- Reads are scoped ------------------------------------------------------

    @Test
    void sessionList_excludesOtherUsersSessions() throws Exception {
        mockMvc.perform(get("/api/chat/sessions").with(asA()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[?(@.title == 'A\\'s session')]").exists())
                .andExpect(jsonPath("$.items[?(@.title == 'B\\'s private session')]").doesNotExist());

        mockMvc.perform(get("/api/chat/sessions").with(asB()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[?(@.title == 'B\\'s private session')]").exists())
                .andExpect(jsonPath("$.items[?(@.title == 'A\\'s session')]").doesNotExist());
    }

    @Test
    void taskList_excludesOtherUsersTasks() throws Exception {
        mockMvc.perform(get("/api/tasks").with(asA()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[?(@.title == 'A\\'s task')]").exists())
                .andExpect(jsonPath("$.items[?(@.title == 'B\\'s private task')]").doesNotExist());
    }

    @Test
    void documentList_excludesOtherUsersDocuments() throws Exception {
        mockMvc.perform(get("/api/documents").with(asA()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[?(@.filename == 'a-report.txt')]").exists())
                .andExpect(jsonPath("$.items[?(@.filename == 'b-private.txt')]").doesNotExist());
    }

    @Test
    void auditTrail_excludesOtherUsersActions() throws Exception {
        mockMvc.perform(get("/api/actions/audit").with(asA()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[?(@.actionId == 'act-b-only')]").doesNotExist());
    }

    // --- Cross-user access is 404, never 403 -----------------------------------
    // A 403 would confirm the resource exists. Folding ownership into the query
    // collapses "not yours" and "not there" into one answer.

    @Test
    void readingAnotherUsersMessages_returns404() throws Exception {
        mockMvc.perform(get("/api/chat/" + sessionB.getId() + "/messages").with(asA()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("CHAT_NOT_FOUND"));
    }

    @Test
    void postingIntoAnotherUsersSession_returns404() throws Exception {
        mockMvc.perform(post("/api/chat/message")
                        .with(asA())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sessionId\":\"" + sessionB.getId() + "\",\"content\":\"Injecting\"}"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("CHAT_NOT_FOUND"));
    }

    @Test
    void updatingAnotherUsersTask_returns404() throws Exception {
        mockMvc.perform(patch("/api/tasks/" + taskB.getId())
                        .with(asA())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"done\"}"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("TASK_NOT_FOUND"));
    }

    @Test
    void deletingAnotherUsersSession_returns404_andLeavesItInPlace() throws Exception {
        mockMvc.perform(delete("/api/chat/sessions/" + sessionB.getId()).with(asA()))
                .andExpect(status().isNotFound());

        mockMvc.perform(get("/api/chat/sessions").with(asB()))
                .andExpect(jsonPath("$.items[?(@.title == 'B\\'s private session')]").exists());
    }

    @Test
    void readingAnotherUsersDocument_returns404() throws Exception {
        mockMvc.perform(get("/api/documents/" + documentB.getId()).with(asA()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("DOCUMENT_NOT_FOUND"));
    }

    @Test
    void downloadingAnotherUsersDocument_returns404() throws Exception {
        mockMvc.perform(get("/api/documents/" + documentB.getId() + "/download").with(asA()))
                .andExpect(status().isNotFound());
    }

    @Test
    void deletingAnotherUsersDocument_returns404_andLeavesItInPlace() throws Exception {
        mockMvc.perform(delete("/api/documents/" + documentB.getId()).with(asA()))
                .andExpect(status().isNotFound());

        mockMvc.perform(get("/api/documents/" + documentB.getId()).with(asB()))
                .andExpect(status().isOk());
    }

    @Test
    void postingAnActionIntoAnotherUsersSession_returns404() throws Exception {
        String body = "{\"actionId\":\"act-cross\",\"sessionId\":\"" + sessionB.getId() + "\","
                + "\"decision\":\"approved\",\"type\":\"create-task\","
                + "\"payload\":{\"title\":\"Task in someone else's session\",\"priority\":\"high\"}}";

        mockMvc.perform(post("/api/ai/actions")
                        .with(asA())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("CHAT_NOT_FOUND"));
    }

    // --- Owners can still do all of the above -----------------------------------

    @Test
    void ownerCanDeleteTheirOwnSession() throws Exception {
        mockMvc.perform(delete("/api/chat/sessions/" + sessionA.getId()).with(asA()))
                .andExpect(status().isNoContent());
    }

    @Test
    void ownerCanDownloadTheirOwnDocument() throws Exception {
        mockMvc.perform(get("/api/documents/" + documentA.getId() + "/download").with(asA()))
                .andExpect(status().isOk())
                .andExpect(header().string("Cache-Control",
                        org.hamcrest.Matchers.containsString("no-store")));
    }

    // --- Input validation --------------------------------------------------------

    @Test
    void actionWithBlankTaskTitle_returns400_notA500() throws Exception {
        String body = "{\"actionId\":\"act-invalid\",\"sessionId\":\"" + sessionA.getId() + "\","
                + "\"decision\":\"approved\",\"type\":\"create-task\","
                + "\"payload\":{\"title\":\"\",\"priority\":\"high\"}}";

        mockMvc.perform(post("/api/ai/actions")
                        .with(asA())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    @Test
    void actionWithMissingPriority_returns400_notA500() throws Exception {
        String body = "{\"actionId\":\"act-invalid-2\",\"sessionId\":\"" + sessionA.getId() + "\","
                + "\"decision\":\"approved\",\"type\":\"create-task\","
                + "\"payload\":{\"title\":\"No priority given\"}}";

        mockMvc.perform(post("/api/ai/actions")
                        .with(asA())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest());
    }

    @Test
    void oversizedMessageContent_returns400() throws Exception {
        String body = "{\"sessionId\":\"" + sessionA.getId() + "\",\"content\":\"" + "x".repeat(4001) + "\"}";

        mockMvc.perform(post("/api/chat/message")
                        .with(asA())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }
}
