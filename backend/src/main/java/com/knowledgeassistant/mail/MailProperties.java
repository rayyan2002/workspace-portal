package com.knowledgeassistant.mail;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Outbound mail settings.
 *
 * @param from      the From address on outgoing mail; for Gmail this must be the
 *                  authenticated account, which rewrites anything else anyway
 * @param fromName  display name shown in the recipient's client
 * @param enabled   an explicit override in BOTH directions. Left unset (null), sending
 *                  turns itself on whenever SMTP credentials are present — see
 *                  {@link EmailService}. Set it only to force the non-obvious case:
 *                  false to silence a configured mailer, true to attempt sending
 *                  against a relay that needs no username.
 */
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        String from,
        String fromName,
        Boolean enabled
) {}
