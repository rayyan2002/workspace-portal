package com.knowledgeassistant.security.jwt;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;

/**
 * Refuses to start with an unsafe signing key outside development.
 *
 * <p>The signing key is the whole security model: anyone holding it can mint a valid
 * token for any user with any role. It is supplied as {@code ${JWT_SECRET:...}}, and the
 * checked-in default exists only so local dev is zero-config — which is precisely what
 * makes it dangerous, because a deployment that simply forgets to set the variable
 * inherits a key that is public in version control.
 *
 * <p>A silent misconfiguration of this kind is worse than a crash, so this turns it into
 * a crash. Dev and test profiles are exempt; every other profile must supply its own key.
 */
@Component
public class JwtSecretValidator implements ApplicationListener<ApplicationReadyEvent> {

    private static final Logger log = LoggerFactory.getLogger(JwtSecretValidator.class);

    /** Must match the default in application.properties. */
    static final String INSECURE_DEFAULT =
            "dev-only-insecure-signing-key-change-me-in-every-real-environment";

    /** HS256 and above require at least 256 bits of key material. */
    private static final int MINIMUM_KEY_BYTES = 32;

    private static final List<String> DEVELOPMENT_PROFILES = List.of("dev", "test", "local");

    private final JwtProperties jwtProperties;
    private final Environment environment;

    public JwtSecretValidator(JwtProperties jwtProperties, Environment environment) {
        this.jwtProperties = jwtProperties;
        this.environment = environment;
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        String secret = jwtProperties.secret();

        if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < MINIMUM_KEY_BYTES) {
            throw new IllegalStateException(
                    "app.jwt.secret must be at least " + MINIMUM_KEY_BYTES + " bytes for HMAC-SHA signing.");
        }

        boolean usingCheckedInDefault = INSECURE_DEFAULT.equals(secret);
        if (!usingCheckedInDefault) {
            return;
        }

        if (isDevelopmentProfile()) {
            log.warn("Using the checked-in development JWT signing key. "
                    + "Set JWT_SECRET before deploying anywhere real — this key is public in version control.");
            return;
        }

        throw new IllegalStateException("""
                Refusing to start: app.jwt.secret is still the development default, which is \
                committed to version control. Anyone with repository access could mint valid \
                tokens for any user.

                Set JWT_SECRET to a private value of at least 32 bytes.

                If this IS a development machine, say so explicitly:
                    SPRING_PROFILES_ACTIVE=dev
                Absence of a profile is no longer treated as development — forgetting to set \
                one must not be what grants the most dangerous configuration.""");
    }

    /**
     * Development is DECLARED, never inferred. Two rules, both changed on Day 17 after the
     * production checklist put them side by side.
     *
     * <p><strong>No profile is no longer development.</strong> It was, and that made the
     * whole protection conditional on something nothing instructed anyone to set: deploying
     * without {@code SPRING_PROFILES_ACTIVE} started the application on the signing key
     * published in this repository, with a warning in a log nobody reads. The safe path
     * required knowing to do something undocumented. Absence of configuration must not grant
     * the most dangerous setting — it is the one state every forgetful deployment is in.
     *
     * <p><strong>EVERY active profile must be a development one.</strong> The old check asked
     * whether ANY was, so {@code prod,local} warned and continued. Adding a profile is an
     * ordinary thing to do and must not be able to switch this off.
     *
     * <p>The cost is real and is paid locally: {@code ./mvnw spring-boot:run} with nothing
     * set now refuses, and the developer is told exactly which variable makes it go. The
     * run configuration in {@code .claude/launch.json} sets it, so the normal path is
     * unaffected.
     */
    private boolean isDevelopmentProfile() {
        String[] active = environment.getActiveProfiles();

        return active.length > 0
                && Arrays.stream(active).allMatch(DEVELOPMENT_PROFILES::contains);
    }
}
