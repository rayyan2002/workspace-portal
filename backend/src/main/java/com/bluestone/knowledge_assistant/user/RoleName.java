package com.bluestone.knowledge_assistant.user;

/**
 * The ROLE_ prefix is part of the stored name on purpose: Spring Security's
 * {@code hasRole('ADMIN')} and {@code @PreAuthorize} add that prefix themselves when
 * comparing against granted authorities, so the authority string must carry it.
 */
public enum RoleName {
    ROLE_USER,
    ROLE_ADMIN
}
