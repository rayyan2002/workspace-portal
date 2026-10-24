package com.knowledgeassistant.admin.dto;

import java.util.UUID;

/**
 * A user as the administration screen needs to see them.
 *
 * <p>Separate from {@code UserDto} on purpose: that one is returned by the auth endpoints to
 * the account's own owner, and widening it to carry role information would publish a user's
 * privileges to every caller that ever receives it. This shape is only ever produced inside
 * {@code /api/admin/**}, which is already behind hasRole('ADMIN').
 *
 * @param admin whether this user currently holds ROLE_ADMIN
 */
public record AdminUserDto(UUID id, String email, String name, boolean admin) {}
