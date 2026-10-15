package com.knowledgeassistant.auth;

import com.knowledgeassistant.support.TestFixtures;
import com.knowledgeassistant.user.RoleName;
import com.knowledgeassistant.user.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * The token lifecycle end to end: login, use, refresh, rotate, revoke.
 */
/*
 * Deliberately NOT @Transactional. These tests assert on what COMMITS — refresh-token
 * rotation, revocation, and the reuse response that runs in its own REQUIRES_NEW
 * transaction. A rollback-only test transaction would both hide that behaviour and
 * deadlock against the inner transaction's row locks. Rows written here are refresh
 * tokens only, and are cleaned up afterwards.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
// Deliberately NOT @Transactional. refreshTokenReuse_revokesTheWholeFamily asserts
// on state that must COMMIT — reuse detection revokes the token family in its own
// transaction, and a rollback-only test transaction would undo it, leaving the test
// green while the mechanism did nothing.
//
// The price is that fixtures here commit too. That leaked ten stray
// user-<uuid>@test.local rows, invisible on an already-populated database and only
// caught by running the suite against a clean one — so cleanUp() runs after each test.
class AuthIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private TestFixtures fixtures;

    private User account;
    private String credentials;

    @org.junit.jupiter.api.AfterEach
    void tearDown() {
        fixtures.cleanUp();
    }

    @BeforeEach
    void setUp() {
        account = fixtures.user(RoleName.ROLE_USER, RoleName.ROLE_ADMIN);
        credentials = "{\"email\":\"" + account.getEmail() + "\",\"password\":\"" + TestFixtures.PASSWORD + "\"}";
    }

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private RefreshTokenRepository refreshTokenRepository;

    @AfterEach
    void clearIssuedTokens() {
        refreshTokenRepository.deleteAll();
    }


    private JsonNode login() throws Exception {
        String body = mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(credentials))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        return objectMapper.readTree(body);
    }

    @Test
    void login_returnsTokenPairAndRoles() throws Exception {
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(credentials))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken").exists())
                .andExpect(jsonPath("$.refreshToken").exists())
                .andExpect(jsonPath("$.tokenType").value("Bearer"))
                .andExpect(jsonPath("$.expiresIn").value(900))       // 15m, in seconds
                .andExpect(jsonPath("$.user.email").value(account.getEmail()))
                .andExpect(jsonPath("$.roles").isArray())
                .andExpect(jsonPath("$.roles[?(@ == 'ROLE_ADMIN')]").exists());
    }

    @Test
    void login_returns401_withWrongPassword() throws Exception {
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"" + account.getEmail() + "\",\"password\":\"wrongpassword\"}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
    }

    @Test
    void login_returns401_withUnknownEmail_sameMessageAsWrongPassword() throws Exception {
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"nobody-at-all@test.local\",\"password\":\"any-password\"}"))
                .andExpect(status().isUnauthorized())
                // Identical message: login must not reveal whether an account exists.
                .andExpect(jsonPath("$.message").value("Invalid email or password"));
    }

    @Test
    void accessToken_fromLogin_authenticatesProtectedEndpoints() throws Exception {
        String accessToken = login().get("accessToken").asString();

        mockMvc.perform(get("/api/chat/sessions").with(fixtures.bearer(accessToken)))
                .andExpect(status().isOk());
    }

    @Test
    void refresh_issuesNewPair_andRotatesTheRefreshToken() throws Exception {
        String originalRefresh = login().get("refreshToken").asString();

        String body = mockMvc.perform(post("/api/auth/refresh")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"refreshToken\":\"" + originalRefresh + "\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken").exists())
                .andExpect(jsonPath("$.refreshToken").exists())
                .andReturn().getResponse().getContentAsString();

        String rotatedRefresh = objectMapper.readTree(body).get("refreshToken").asString();
        assertThat(rotatedRefresh).isNotEqualTo(originalRefresh);
    }

    @Test
    void refresh_returns401_whenTheSameTokenIsUsedTwice() throws Exception {
        String refreshToken = login().get("refreshToken").asString();
        String request = "{\"refreshToken\":\"" + refreshToken + "\"}";

        mockMvc.perform(post("/api/auth/refresh").contentType(MediaType.APPLICATION_JSON).content(request))
                .andExpect(status().isOk());

        // Rotation is single-use: replaying a spent token is treated as compromise.
        mockMvc.perform(post("/api/auth/refresh").contentType(MediaType.APPLICATION_JSON).content(request))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
    }

    @Test
    void refreshTokenReuse_revokesTheWholeFamily() throws Exception {
        String original = login().get("refreshToken").asString();

        String rotatedBody = mockMvc.perform(post("/api/auth/refresh")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"refreshToken\":\"" + original + "\"}"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        String rotated = objectMapper.readTree(rotatedBody).get("refreshToken").asString();

        // Replaying the spent token is treated as compromise...
        mockMvc.perform(post("/api/auth/refresh")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"refreshToken\":\"" + original + "\"}"))
                .andExpect(status().isUnauthorized());

        // ...so the token that legitimately replaced it must die too. This only holds
        // because the revocation commits in its own transaction; sharing the caller's
        // transaction would let the 401 above roll the revocation back.
        mockMvc.perform(post("/api/auth/refresh")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"refreshToken\":\"" + rotated + "\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void refresh_returns401_withAnUnknownToken() throws Exception {
        mockMvc.perform(post("/api/auth/refresh")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"refreshToken\":\"not-a-real-refresh-token\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void logout_revokesTheRefreshToken() throws Exception {
        JsonNode session = login();
        String accessToken = session.get("accessToken").asString();
        String refreshToken = session.get("refreshToken").asString();
        String request = "{\"refreshToken\":\"" + refreshToken + "\"}";

        mockMvc.perform(post("/api/auth/logout")
                        .with(fixtures.bearer(accessToken))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(request))
                .andExpect(status().isNoContent());

        mockMvc.perform(post("/api/auth/refresh")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(request))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void logoutAll_revokesEveryRefreshTokenForTheUser() throws Exception {
        String firstRefresh = login().get("refreshToken").asString();
        JsonNode second = login();

        mockMvc.perform(post("/api/auth/logout-all")
                        .with(fixtures.bearer(second.get("accessToken").asString())))
                .andExpect(status().isNoContent());

        for (String refreshToken : new String[]{firstRefresh, second.get("refreshToken").asString()}) {
            mockMvc.perform(post("/api/auth/refresh")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"refreshToken\":\"" + refreshToken + "\"}"))
                    .andExpect(status().isUnauthorized());
        }
    }
}
