package com.knowledgeassistant.mail;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The rule that decides whether mail is actually sent.
 *
 * <p>Worth pinning because getting it wrong is invisible at runtime: forgot-password
 * answers 202 either way, deliberately, so a mailer that silently does nothing looks
 * exactly like one that works.
 */
class EmailServiceTest {

    @Test
    void sendingIsOff_whenNoCredentialsAndNoOverride() {
        assertThat(EmailService.resolveSendingEnabled(null, "")).isFalse();
        assertThat(EmailService.resolveSendingEnabled(null, "   ")).isFalse();
        assertThat(EmailService.resolveSendingEnabled(null, null)).isFalse();
    }

    @Test
    void sendingTurnsItselfOn_asSoonAsAUsernameExists() {
        // Supplying credentials is unambiguous intent to send; requiring a second flag
        // as well is what produced "configured correctly, still no mail".
        assertThat(EmailService.resolveSendingEnabled(null, "someone@gmail.com")).isTrue();
    }

    @Test
    void explicitOverrideWins_inBothDirections() {
        // false silences a fully configured mailer...
        assertThat(EmailService.resolveSendingEnabled(false, "someone@gmail.com")).isFalse();
        // ...and true attempts a relay that needs no username.
        assertThat(EmailService.resolveSendingEnabled(true, "")).isTrue();
    }
}
