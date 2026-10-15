package com.knowledgeassistant.security.jwt;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.mock.env.MockEnvironment;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Day 17: the one configuration failure that is a security incident rather than an outage.
 *
 * <p>This behaviour has existed since Month 2 and had <strong>no test</strong>. It was
 * discovered during Day 17's audit, when the production checklist needed to state what
 * happens if {@code JWT_SECRET} is left unset — and the only available answer was "read the
 * class and see". That is exactly the kind of claim this project does not make: the
 * checklist asserts that a deployment with the default key refuses to start, so something
 * had better fail when it does not.
 *
 * <p><strong>Why it is worse than an outage.</strong> The default signing key is committed to
 * this repository. Anyone with read access could mint a valid token for any user. A service
 * that starts with it is not degraded, it is wide open, and nothing about its behaviour would
 * reveal that.
 *
 * <p>The validator is exercised directly rather than through a Spring context: it is an
 * {@link ApplicationReadyEvent} listener, so a context test would have to boot the whole
 * application once per case to assert four branches of one method.
 */
class JwtSecretValidatorTest {

    /** The value committed in application.properties. */
    private static final String CHECKED_IN_DEFAULT =
            "dev-only-insecure-signing-key-change-me-in-every-real-environment";

    private static final String REAL_SECRET =
            "a-private-value-of-at-least-thirty-two-bytes-length";

    private JwtSecretValidator validator(String secret, String... activeProfiles) {
        MockEnvironment environment = new MockEnvironment();
        environment.setActiveProfiles(activeProfiles);
        return new JwtSecretValidator(
                new JwtProperties(secret, "knowledge-assistant",
                        Duration.ofMinutes(15), Duration.ofDays(7)),
                environment);
    }

    private void validate(JwtSecretValidator validator) {
        validator.onApplicationEvent(null);
    }

    // --- the dangerous case ----------------------------------------------------

    @Test
    void theCheckedInDefaultRefusesToStartOutsideDevelopment() {
        // THE ASSERTION THE PRODUCTION CHECKLIST RESTS ON. A deployment that forgot
        // JWT_SECRET must not come up.
        IllegalStateException refused = assertThrows(IllegalStateException.class,
                () -> validate(validator(CHECKED_IN_DEFAULT, "prod")));

        assertTrue(refused.getMessage().contains("JWT_SECRET"),
                "the message must name the variable to set: " + refused.getMessage());
        assertTrue(refused.getMessage().contains("version control"),
                "and say why it is dangerous, or it reads like a policy nag");
    }

    @Test
    void theCheckedInDefaultOnlyWarnsInDevelopment() {
        // Local development must not require a secret to be invented before anything runs.
        // This is the branch that makes the strict one acceptable.
        assertDoesNotThrow(() -> validate(validator(CHECKED_IN_DEFAULT, "dev")));
        assertDoesNotThrow(() -> validate(validator(CHECKED_IN_DEFAULT, "test")));
        assertDoesNotThrow(() -> validate(validator(CHECKED_IN_DEFAULT, "local")));
    }

    @Test
    void noProfileAtAllIsREFUSED() {
        // INVERTED ON DAY 17, and this is the assertion that matters most in the file.
        //
        // It used to pass with assertDoesNotThrow, and I wrote it that way as a convenience
        // for local development — which it genuinely is. The consequence only became visible
        // when the production checklist asked what happens on a deployment that forgets
        // SPRING_PROFILES_ACTIVE: the answer was "starts on the signing key published in
        // this repository, and warns". The protection was real and its trigger condition was
        // undocumented, so the safe path required knowing to do something nothing told you
        // to do.
        //
        // Absence of configuration is the state every forgetful deployment is in. It must
        // not be the state that grants the most dangerous setting.
        IllegalStateException refused = assertThrows(IllegalStateException.class,
                () -> validate(validator(CHECKED_IN_DEFAULT)));

        assertTrue(refused.getMessage().contains("SPRING_PROFILES_ACTIVE"),
                "a developer hitting this locally must be told exactly what makes it go: "
                        + refused.getMessage());
    }

    @Test
    void aMixedProfileListContainingProdIsRefused() {
        // ALSO INVERTED ON DAY 17. The old rule asked whether ANY active profile was a
        // development one, so `prod,local` warned and continued — and adding a profile is an
        // ordinary thing to do, not something that should be able to switch a security
        // control off. EVERY active profile must now be a development profile.
        assertThrows(IllegalStateException.class,
                () -> validate(validator(CHECKED_IN_DEFAULT, "prod", "local")));
        assertThrows(IllegalStateException.class,
                () -> validate(validator(CHECKED_IN_DEFAULT, "dev", "prod")));
    }

    @Test
    void severalDevelopmentProfilesTogetherStillWarn() {
        // The tightening must not punish a legitimate local combination.
        assertDoesNotThrow(() -> validate(validator(CHECKED_IN_DEFAULT, "dev", "local")));
    }

    // --- the key has to be usable at all ---------------------------------------

    @Test
    void aSecretShorterThanTheSigningAlgorithmNeedsIsRefusedEverywhere() {
        // Not a policy preference: HMAC-SHA256 requires a key of at least 256 bits, so a
        // shorter one cannot sign. Refused even in development, because there is no
        // configuration in which it works.
        for (String profile : new String[]{"dev", "test", "prod"}) {
            IllegalStateException refused = assertThrows(IllegalStateException.class,
                    () -> validate(validator("too-short", profile)),
                    "a short key must be refused under the " + profile + " profile");
            assertTrue(refused.getMessage().contains("32"),
                    "the message must say how long it needs to be");
        }
    }

    @Test
    void aMissingSecretIsRefused() {
        assertThrows(IllegalStateException.class, () -> validate(validator(null, "dev")));
    }

    // --- the configuration that should work ------------------------------------

    @Test
    void aPrivateSecretOfSufficientLengthStartsAnywhere() {
        assertDoesNotThrow(() -> validate(validator(REAL_SECRET, "prod")));
        assertDoesNotThrow(() -> validate(validator(REAL_SECRET, "dev")));
    }
}
