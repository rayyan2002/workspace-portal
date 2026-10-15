package com.knowledgeassistant.mail;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * Sends mail, or logs it when sending is switched off.
 *
 * <p>The disabled path is not a stub — it is how the password-reset flow is exercised
 * in development and CI. Requiring real SMTP credentials to test a reset would mean
 * either committing a Gmail app password or leaving the feature untested; logging the
 * message body gives a working reset link with neither.
 */
@Service
public class EmailService {

    private static final Logger log = LoggerFactory.getLogger(EmailService.class);

    private final JavaMailSender mailSender;
    private final MailProperties properties;
    private final boolean sendingEnabled;

    public EmailService(JavaMailSender mailSender,
                        MailProperties properties,
                        @Value("${spring.mail.username:}") String smtpUsername) {
        this.mailSender = mailSender;
        this.properties = properties;
        this.sendingEnabled = resolveSendingEnabled(properties.enabled(), smtpUsername);
    }

    /**
     * Sending turns itself on as soon as credentials exist.
     *
     * <p>Requiring a separate on/off flag alongside the username meant configuring the
     * mailer correctly and still getting no mail, with a 202 and a silent log line as
     * the only evidence. Supplying a username is unambiguous intent to send, so that is
     * what the decision keys on; the flag stays available to force either direction.
     */
    static boolean resolveSendingEnabled(Boolean explicitOverride, String smtpUsername) {
        if (explicitOverride != null) {
            return explicitOverride;
        }
        return StringUtils.hasText(smtpUsername);
    }

    /**
     * Says plainly at startup which mode is active.
     *
     * <p>A misconfigured mailer is otherwise invisible: forgot-password answers 202
     * whether or not the mail went, deliberately, so that the endpoint cannot be used
     * to discover which addresses have accounts.
     */
    @PostConstruct
    void logMailMode() {
        if (sendingEnabled) {
            log.info("Mail sending ENABLED — messages will be delivered from {}", properties.from());
        } else {
            log.warn("Mail sending DISABLED — messages are written to this log instead. "
                    + "Set MAIL_USERNAME and MAIL_PASSWORD to send for real "
                    + "(Gmail requires an App Password, not the account password).");
        }
    }

    public void send(String to, String subject, String body) {
        if (!sendingEnabled) {
            log.warn("""
                    
                    ============ MAIL NOT SENT (no SMTP credentials configured) ==============
                    To      : {}
                    Subject : {}
                    
                    {}
                    ==========================================================================
                    """, to, subject, body);
            return;
        }

        try {
            SimpleMailMessage message = new SimpleMailMessage();
            message.setFrom(properties.from());
            message.setTo(to);
            message.setSubject(subject);
            message.setText(body);

            mailSender.send(message);
            log.info("Sent '{}' to {}", subject, to);

        } catch (Exception e) {
            // Never rethrow to the caller. A password-reset endpoint that fails loudly
            // when SMTP is down tells an attacker the address exists, and leaves the
            // user staring at an error for something they cannot fix.
            log.error("Failed to send '{}' to {}: {}", subject, to, e.getMessage());
        }
    }
}
