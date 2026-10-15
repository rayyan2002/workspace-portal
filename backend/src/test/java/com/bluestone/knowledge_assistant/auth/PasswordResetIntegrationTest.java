package com.bluestone.knowledge_assistant.auth;

import com.bluestone.knowledge_assistant.support.TestFixtures;
import com.bluestone.knowledge_assistant.user.User;
import com.bluestone.knowledge_assistant.user.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import java.lang.reflect.Field;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * The reset flow end to end.
 *
 * <p>The emailed token is generated inside the service and never returned by the API —
 * which is the point — so these tests mint their own token rows directly, storing the
 * same SHA-256 digest the service would. That exercises every code path except the
 * SMTP send itself.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class PasswordResetIntegrationTest {

    private static final String ORIGINAL_PASSWORD = TestFixtures.PASSWORD;

    @Autowired private MockMvc mockMvc;
    @Autowired private PasswordResetTokenRepository tokenRepository;
    @Autowired private UserRepository userRepository;
    @Autowired private TestFixtures fixtures;

    private User account;

    @BeforeEach
    void setUp() {
        account = fixtures.user();
    }

    private String loginBody(String password) {
        return "{\"email\":\"" + account.getEmail() + "\",\"password\":\"" + password + "\"}";
    }

    private static String sha256(String value) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
    }

    /** Creates a live token for this test's account and returns its plaintext. */
    private String issueToken(Instant expiresAt) throws Exception {
        String raw = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(UUID.randomUUID().toString().getBytes(StandardCharsets.UTF_8));

        tokenRepository.save(new PasswordResetToken(
                userRepository.getReferenceById(account.getId()), sha256(raw), expiresAt, Instant.now()));

        return raw;
    }

    private void resetWith(String token, String newPassword, int expectedStatus) throws Exception {
        mockMvc.perform(post("/api/auth/reset-password")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"token\":\"" + token + "\",\"newPassword\":\"" + newPassword + "\"}"))
                .andExpect(status().is(expectedStatus));
    }

    @Test
    void forgotPassword_returns202_forAKnownAddress() throws Exception {
        mockMvc.perform(post("/api/auth/forgot-password")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"" + account.getEmail() + "\"}"))
                .andExpect(status().isAccepted());
    }

    @Test
    void forgotPassword_returns202_forAnUnknownAddress_too() throws Exception {
        // Identical response, so the endpoint cannot be used to discover which
        // addresses have accounts.
        mockMvc.perform(post("/api/auth/forgot-password")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"nobody-at-all@bluestone.com\"}"))
                .andExpect(status().isAccepted());
    }

    @Test
    void forgotPassword_storesOnlyAHash_neverThePlaintextToken() throws Exception {
        mockMvc.perform(post("/api/auth/forgot-password")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"" + account.getEmail() + "\"}"))
                .andExpect(status().isAccepted());

        var stored = tokenRepository.findAll();
        assertThat(stored).isNotEmpty();

        for (PasswordResetToken token : stored) {
            Field field = PasswordResetToken.class.getDeclaredField("tokenHash");
            field.setAccessible(true);
            String hash = (String) field.get(token);

            // A SHA-256 hex digest and nothing that could be used as a link.
            assertThat(hash).hasSize(64).matches("[0-9a-f]{64}");
        }
    }

    @Test
    void resetPassword_setsTheNewPassword_andRetiresTheOldOne() throws Exception {
        String token = issueToken(Instant.now().plusSeconds(600));

        resetWith(token, "brand-new-password", 204);

        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody("brand-new-password")))
                .andExpect(status().isOk());

        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(ORIGINAL_PASSWORD)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void resetPassword_revokesExistingSessions() throws Exception {
        // A session established BEFORE the reset.
        String refreshToken = com.jayway.jsonpath.JsonPath.read(
                mockMvc.perform(post("/api/auth/login")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(loginBody(ORIGINAL_PASSWORD)))
                        .andReturn().getResponse().getContentAsString(),
                "$.refreshToken");

        resetWith(issueToken(Instant.now().plusSeconds(600)), "brand-new-password", 204);

        // Resetting a password is what someone does when they think they are
        // compromised. Leaving old sessions alive would defeat the whole point.
        mockMvc.perform(post("/api/auth/refresh")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"refreshToken\":\"" + refreshToken + "\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void resetPassword_returns401_whenTheTokenIsReused() throws Exception {
        String token = issueToken(Instant.now().plusSeconds(600));

        resetWith(token, "brand-new-password", 204);
        resetWith(token, "another-password-entirely", 401);

        // The second attempt must not have taken effect.
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody("another-password-entirely")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void resetPassword_returns401_whenTheTokenHasExpired() throws Exception {
        String expired = issueToken(Instant.now().minusSeconds(60));

        resetWith(expired, "brand-new-password", 401);
    }

    @Test
    void resetPassword_returns401_onAnUnknownToken() throws Exception {
        resetWith("not-a-real-token", "brand-new-password", 401);
    }

    @Test
    void resetPassword_returns400_onAShortPassword() throws Exception {
        String token = issueToken(Instant.now().plusSeconds(600));

        mockMvc.perform(post("/api/auth/reset-password")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"token\":\"" + token + "\",\"newPassword\":\"short\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }
}
