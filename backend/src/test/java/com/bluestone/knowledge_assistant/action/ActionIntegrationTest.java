package com.bluestone.knowledge_assistant.action;

import com.bluestone.knowledge_assistant.chat.ChatSession;
import com.bluestone.knowledge_assistant.support.TestFixtures;
import com.bluestone.knowledge_assistant.user.User;
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

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class ActionIntegrationTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private TestFixtures fixtures;

    private User owner;
    private ChatSession session;

    @BeforeEach
    void setUp() {
        owner = fixtures.user();
        session = fixtures.session(owner, "Governance session");
    }

    private RequestPostProcessor asOwner() { return fixtures.as(owner); }

    @Test
    void getTasks_returns200() throws Exception {
        mockMvc.perform(get("/api/tasks").with(asOwner()))
                .andExpect(status().isOk());
    }

    @Test
    void processAction_returns200_andCreatesTask_whenApproved() throws Exception {
        String body = "{\"actionId\":\"act-it-1\",\"sessionId\":\"" + session.getId() + "\","
                + "\"decision\":\"approved\",\"type\":\"create-task\","
                + "\"payload\":{\"title\":\"Integration test task\",\"priority\":\"high\"}}";

        mockMvc.perform(post("/api/ai/actions")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("completed"))
                .andExpect(jsonPath("$.result.title").value("Integration test task"));

        mockMvc.perform(get("/api/tasks").with(asOwner()))
                .andExpect(jsonPath("$.items[?(@.title == 'Integration test task')]").exists());
    }

    @Test
    void processAction_returns200_andNoTask_whenRejected() throws Exception {
        String body = "{\"actionId\":\"act-it-2\",\"sessionId\":\"" + session.getId() + "\","
                + "\"decision\":\"rejected\",\"type\":\"create-task\","
                + "\"payload\":{\"title\":\"Should not exist\",\"priority\":\"low\"}}";

        mockMvc.perform(post("/api/ai/actions")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("rejected"))
                .andExpect(jsonPath("$.result").doesNotExist());

        mockMvc.perform(get("/api/tasks").with(asOwner()))
                .andExpect(jsonPath("$.items[?(@.title == 'Should not exist')]").doesNotExist());
    }

    @Test
    void rejectedAction_isStillAudited() throws Exception {
        String body = "{\"actionId\":\"act-audited-rejection\",\"sessionId\":\"" + session.getId() + "\","
                + "\"decision\":\"rejected\",\"type\":\"create-task\","
                + "\"payload\":{\"title\":\"Declined by the human\",\"priority\":\"low\"}}";

        mockMvc.perform(post("/api/ai/actions")
                        .with(asOwner())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk());

        // The whole point of human-in-the-loop: a refusal is recorded, not discarded.
        mockMvc.perform(get("/api/actions/audit").with(asOwner()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[?(@.actionId == 'act-audited-rejection')]").exists());
    }
}
