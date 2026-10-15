package com.knowledgeassistant.config;

import com.knowledgeassistant.genai.GenAiProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.validation.autoconfigure.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Day 17: a misconfigured service must refuse to start, not start and answer nothing.
 *
 * <p><strong>MEASURED BEFORE ANY OF THIS EXISTED: eight deliberately bad values, eight
 * accepted.</strong> {@code app.genai.*} bound without complaint to {@code top-k=0},
 * {@code min-score=5.0}, {@code timeout=0s} and {@code base-url=not-a-url}. The application
 * started cleanly every time.
 *
 * <p>What makes that worse than a startup crash is WHERE the failure surfaces. Python
 * validates the same two values on its side — {@code top_k} has {@code ge=1} and
 * {@code min_score} is bounded to the cosine range — so a Spring misconfiguration becomes a
 * 422 from the GenAI service, and the user is told "the AI service refused the request".
 * True, and pointing at the wrong service. Spring sent the invalid value; Python only
 * noticed.
 *
 * <p>These tests are the probe that measured it, kept and inverted: each case asserted to be
 * REFUSED now, so a constraint removed in a refactor fails here rather than in production.
 * They use {@link ApplicationContextRunner} — no web server, no database, no GenAI process —
 * because a configuration test that needs infrastructure is one nobody runs.
 */
class GenAiPropertiesValidationTest {

    @EnableConfigurationProperties(GenAiProperties.class)
    static class Harness {
    }

    /** A complete, valid configuration. Each test overrides exactly one value. */
    private static final String[] VALID = {
            "app.genai.base-url=http://127.0.0.1:8000",
            "app.genai.timeout=150s",
            "app.genai.connect-timeout=2s",
            "app.genai.top-k=5",
            "app.genai.history-turns=6",
            "app.genai.min-score=0.60",
    };

    private ApplicationContextRunner runner(String... overrides) {
        String[] properties = new String[VALID.length + overrides.length];
        System.arraycopy(VALID, 0, properties, 0, VALID.length);
        System.arraycopy(overrides, 0, properties, VALID.length, overrides.length);
        return new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        ConfigurationPropertiesAutoConfiguration.class,
                        ValidationAutoConfiguration.class))
                .withUserConfiguration(Harness.class)
                .withPropertyValues(properties);
    }

    private void refuses(String override) {
        runner(override).run(context ->
                assertThat(context).as("startup should have been refused for: %s", override)
                        .hasFailed());
    }

    // --- the configuration that is actually shipped -----------------------------

    @Test
    void theValidConfigurationBinds() {
        // Guards against constraints so strict that the real settings cannot load — the way
        // a validation change breaks everything rather than nothing.
        runner().run(context -> {
            assertThat(context).hasNotFailed();
            GenAiProperties properties = context.getBean(GenAiProperties.class);
            assertThat(properties.topK()).isEqualTo(5);
            assertThat(properties.minScore()).isEqualTo(0.60);
            assertThat(properties.timeout().toSeconds()).isEqualTo(150);
        });
    }

    // --- values the far side rejects, caught here instead ------------------------

    @Test
    void topKBelowOneIsRefused() {
        // Asks the GenAI service for NO chunks. Its RetrievalRequest declares top_k with
        // ge=1, so this is a 422 on every question a user asks — attributed to the AI
        // service rather than to this file.
        refuses("app.genai.top-k=0");
        refuses("app.genai.top-k=-5");
    }

    @Test
    void aMinScoreOutsideTheCosineRangeIsRefused() {
        // Not a preference — arithmetic. Cosine similarity lives in [-1, 1], so a floor of
        // 5.0 can never be cleared by anything and every question returns
        // insufficient_context while the service looks perfectly healthy.
        refuses("app.genai.min-score=5.0");
        refuses("app.genai.min-score=-9");
    }

    @Test
    void aNegativeHistoryWindowIsRefused() {
        refuses("app.genai.history-turns=-1");
    }

    // --- values that make every request fail in a way that mimics an outage ------

    @Test
    void aZeroOrNegativeTimeoutIsRefused() {
        // @NotNull is satisfied by 0s, and Jakarta Validation has no duration minimum, so
        // this needs the record's compact constructor. A zero read timeout fails every
        // request the instant it is sent — indistinguishable from the service being down.
        refuses("app.genai.timeout=0s");
        refuses("app.genai.connect-timeout=0s");
    }

    @Test
    void aBaseUrlThatIsNotAUrlIsRefused() {
        refuses("app.genai.base-url=not-a-url");
        refuses("app.genai.base-url=");
        refuses("app.genai.base-url=   ");
    }

    @Test
    void aNonHttpSchemeIsRefused() {
        // The client speaks HTTP. A scheme it cannot use fails at the first call, which is
        // the first question a user asks.
        refuses("app.genai.base-url=ftp://127.0.0.1:8000");
    }

    // --- the message has to be actionable ---------------------------------------

    @Test
    void theFailureNamesThePropertyAndSaysWhatIsWrongWithIt() {
        // A validation failure that says "binding failed" sends someone to read source code.
        // The property key is what appears in application.properties, so it is what the
        // message must carry.
        runner("app.genai.min-score=5.0").run(context -> {
            assertThat(context).hasFailed();
            String message = rootMessage(context.getStartupFailure());
            assertThat(message).contains("app.genai.min-score");
            assertThat(message).contains("cosine");
        });
    }

    @Test
    void theBaseUrlFailureNamesTheEnvironmentVariableBehindIt() {
        // app.genai.base-url is itself ${GENAI_BASE_URL:...}, so the property name alone
        // sends an operator to the wrong place — they set the variable, not the key.
        runner("app.genai.base-url=not-a-url").run(context -> {
            assertThat(context).hasFailed();
            assertThat(rootMessage(context.getStartupFailure())).contains("GENAI_BASE_URL");
        });
    }

    private static String rootMessage(Throwable failure) {
        StringBuilder all = new StringBuilder();
        for (Throwable t = failure; t != null; t = t.getCause()) {
            all.append(t.getMessage()).append('\n');
        }
        return all.toString();
    }
}
