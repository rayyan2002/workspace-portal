package com.knowledgeassistant.observability;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.knowledgeassistant.support.TestFixtures;
import com.knowledgeassistant.user.User;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * Nothing that can authenticate a user may reach the logs.
 *
 * <p>This exists because it was NOT true: Logbook was configured at TRACE, which logs
 * request and response bodies, so every login wrote the plaintext password, the issued
 * JWT, and the refresh token to the console. Removing Logbook fixed it; this test is
 * what stops it coming back, because the next person to add request logging will not
 * know that history.
 *
 * <p>Capture is attached to the ROOT logger deliberately. Attaching to a named logger
 * would only observe the loggers this test already knows about — and the leak it is
 * guarding against arrives from a library nobody anticipated, under its own name. A
 * test watching the wrong stream passes while the leak continues, which is worse than
 * no test at all.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class LogRedactionTest {

    private static final String PASSWORD = TestFixtures.PASSWORD;

    @Autowired private MockMvc mockMvc;
    @Autowired private TestFixtures fixtures;

    private ListAppender<ILoggingEvent> captured;
    private Logger rootLogger;
    private User account;

    @BeforeEach
    void setUp() {
        account = fixtures.user();

        rootLogger = (Logger) LoggerFactory.getLogger(org.slf4j.Logger.ROOT_LOGGER_NAME);
        captured = new ListAppender<>();
        captured.start();
        rootLogger.addAppender(captured);
    }

    @AfterEach
    void tearDown() {
        rootLogger.detachAppender(captured);
        captured.stop();
    }

    /** Everything written to any logger during the test, message and MDC alike. */
    private String everythingLogged() {
        return captured.list.stream()
                .map(event -> event.getFormattedMessage() + " " + event.getMDCPropertyMap())
                .collect(Collectors.joining("\n"));
    }

    @Test
    void loginDoesNotLogThePassword() throws Exception {
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"" + account.getEmail() + "\",\"password\":\"" + PASSWORD + "\"}"));

        assertThat(everythingLogged())
                .as("the plaintext password must never reach any logger")
                .doesNotContain(PASSWORD);
    }

    @Test
    void loginDoesNotLogTheIssuedTokens() throws Exception {
        String body = mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"" + account.getEmail() + "\",\"password\":\"" + PASSWORD + "\"}"))
                .andReturn().getResponse().getContentAsString();

        String logged = everythingLogged();

        // A JWT is recognisable by its header segment; the refresh token is opaque, so
        // it is pulled out of the response and searched for literally.
        assertThat(logged)
                .as("the issued access token must not be logged")
                .doesNotContain("eyJhbGciOi");

        String refreshToken = com.jayway.jsonpath.JsonPath.read(body, "$.refreshToken");
        assertThat(logged)
                .as("the issued refresh token must not be logged")
                .doesNotContain(refreshToken);
    }

    @Test
    void registrationDoesNotLogTheChosenPassword() throws Exception {
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Log Check\",\"email\":\"log-check@test.local\","
                                + "\"password\":\"" + PASSWORD + "\"}"));

        assertThat(everythingLogged()).doesNotContain(PASSWORD);
    }

    /**
     * A record's generated toString() includes every component, so any log line or
     * exception message that interpolates one of these DTOs would print the secret.
     * Overriding toString() makes that impossible rather than merely discouraged.
     */
    @Test
    void secretCarryingDtosDoNotStringifyTheirSecrets() {
        var login = new com.knowledgeassistant.auth.dto.LoginRequest("a@b.com", PASSWORD);
        var register = new com.knowledgeassistant.auth.dto.RegisterRequest("N", "a@b.com", PASSWORD);
        var reset = new com.knowledgeassistant.auth.dto.ResetPasswordRequest("tok-abc", PASSWORD);
        var refresh = new com.knowledgeassistant.auth.dto.RefreshTokenRequest("refresh-xyz");

        assertThat(List.of(login.toString(), register.toString(), reset.toString(), refresh.toString()))
                .as("no DTO may stringify a credential")
                .allSatisfy(text -> assertThat(text)
                        .doesNotContain(PASSWORD)
                        .doesNotContain("tok-abc")
                        .doesNotContain("refresh-xyz"));
    }
}
