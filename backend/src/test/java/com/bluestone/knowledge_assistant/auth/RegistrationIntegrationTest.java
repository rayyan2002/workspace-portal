package com.bluestone.knowledge_assistant.auth;

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
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class RegistrationIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private TestFixtures fixtures;

    private User existing;

    @BeforeEach
    void setUp() {
        // An account this test owns, rather than whichever one the seed data happens
        // to contain — that coupling is what broke the suite when the demo users were
        // retired.
        existing = fixtures.user();
    }

    private static String signUp(String name, String email, String password) {
        return """
                {"name":"%s","email":"%s","password":"%s"}
                """.formatted(name, email, password);
    }

    @Test
    void register_createsAccount_andReturns201() throws Exception {
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(signUp("New Person", "new.person@bluestone.com", "a-good-password")))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.email").value("new.person@bluestone.com"))
                .andExpect(jsonPath("$.name").value("New Person"))
                .andExpect(jsonPath("$.id").exists())
                // The password must never come back, encoded or otherwise.
                .andExpect(jsonPath("$.password").doesNotExist());
    }

    @Test
    void register_thenLogin_worksWithTheChosenPassword() throws Exception {
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(signUp("Login Me", "login.me@bluestone.com", "a-good-password")))
                .andExpect(status().isCreated());

        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"login.me@bluestone.com\",\"password\":\"a-good-password\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken").exists())
                // Self-service sign-up must never confer admin.
                .andExpect(jsonPath("$.roles[?(@ == 'ROLE_USER')]").exists())
                .andExpect(jsonPath("$.roles[?(@ == 'ROLE_ADMIN')]").doesNotExist());
    }

    @Test
    void register_newAccountSeesOnlyItsOwnEmptyWorkspace() throws Exception {
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(signUp("Fresh", "fresh@bluestone.com", "a-good-password")))
                .andExpect(status().isCreated());

        String token = com.jayway.jsonpath.JsonPath.read(
                mockMvc.perform(post("/api/auth/login")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"email\":\"fresh@bluestone.com\",\"password\":\"a-good-password\"}"))
                        .andReturn().getResponse().getContentAsString(),
                "$.accessToken");

        // Scoping applies to brand-new users too: no inherited documents or chats.
        mockMvc.perform(get("/api/documents").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(0));

        mockMvc.perform(get("/api/chat/sessions").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(0));
    }

    @Test
    void register_returns409_whenEmailAlreadyExists() throws Exception {
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(signUp("Duplicate", existing.getEmail(), "a-good-password")))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("EMAIL_ALREADY_REGISTERED"));
    }

    @Test
    void register_normalisesEmailCase() throws Exception {
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(signUp("Shouty", "SHOUTY@BLUESTONE.COM", "a-good-password")))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.email").value("shouty@bluestone.com"));

        // ...so the same address in a different case cannot register twice.
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(signUp("Shouty Again", "shouty@bluestone.com", "a-good-password")))
                .andExpect(status().isConflict());
    }

    @Test
    void register_returns400_onShortPassword() throws Exception {
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(signUp("Weak", "weak@bluestone.com", "short")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    @Test
    void register_returns400_onInvalidEmail() throws Exception {
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(signUp("Bad Email", "not-an-email", "a-good-password")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }
}
