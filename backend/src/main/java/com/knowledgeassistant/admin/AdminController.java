package com.knowledgeassistant.admin;

import com.knowledgeassistant.admin.dto.AdminUserDto;
import com.knowledgeassistant.security.annotation.CurrentUserId;
import com.knowledgeassistant.user.RoleName;
import com.knowledgeassistant.common.PageRequestFactory;
import com.knowledgeassistant.common.dto.PageResponse;
import com.knowledgeassistant.user.UserRepository;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

/**
 * Role-restricted endpoints.
 *
 * <p>Guarded twice on purpose: the URL rule in {@code SecurityConfig} covers
 * {@code /api/admin/**} as a whole, and {@code @PreAuthorize} states the requirement on
 * the method itself so it survives a controller being remapped to a different path.
 */
@RestController
@RequestMapping("/api/admin")
@PreAuthorize("hasRole('ADMIN')")
@Tag(name = "Administration", description = "Endpoints restricted to ROLE_ADMIN")
public class AdminController {

    private final UserRepository userRepository;
    private final AdminUserService adminUserService;

    public AdminController(UserRepository userRepository,
                           AdminUserService adminUserService) {
        this.userRepository = userRepository;
        this.adminUserService = adminUserService;
    }

    /**
     * Paged like every other list endpoint.
     *
     * It was not, until the Day-21 audit wired a UI to it and the page broke on
     * `undefined.map`. Nothing had ever called it, so when pagination landed on Day 19
     * this endpoint was simply missed — it kept returning a bare array while the
     * contract said `{ items, total, page, size }`. A path-level diff cannot catch
     * that: the endpoint existed and was correct by URL, and only wrong by SHAPE.
     */
    @GetMapping("/users")
    @Operation(summary = "List all users, paged (admin only)")
    public ResponseEntity<PageResponse<AdminUserDto>> listUsers(
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size) {

        // ONE extra query for the whole page, not one per user — the N+1 QueryCountTest
        // exists to catch, and this list is paged so the cost would scale with page size.
        var admins = userRepository.findIdsByRoleName(RoleName.ROLE_ADMIN);
        return ResponseEntity.ok(PageResponse.from(
                userRepository.findAll(PageRequestFactory.of(page, size)),
                user -> new AdminUserDto(user.getId(), user.getEmail(), user.getName(),
                        admins.contains(user.getId()))));
    }

    /**
     * Grants ROLE_ADMIN to another account.
     *
     * <p>PUT rather than POST because it is idempotent: granting admin to somebody who
     * already has it is a no-op, not a second grant, and a double-clicked button should not
     * mean anything different from a single click.
     */
    @PutMapping("/users/{userId}/admin")
    @Operation(summary = "Grant administrator access to a user (admin only)")
    public ResponseEntity<Void> grantAdmin(@PathVariable UUID userId,
                                           @CurrentUserId UUID actingUserId) {
        adminUserService.grantAdmin(userId, actingUserId);
        return ResponseEntity.noContent().build();
    }

    /**
     * Removes ROLE_ADMIN from another account.
     *
     * <p>Refuses to remove your OWN access, and refuses to remove the LAST administrator —
     * both are one-way doors, because the endpoint that would undo them is itself behind
     * hasRole('ADMIN').
     */
    @DeleteMapping("/users/{userId}/admin")
    @Operation(summary = "Revoke administrator access from a user (admin only)")
    public ResponseEntity<Void> revokeAdmin(@PathVariable UUID userId,
                                            @CurrentUserId UUID actingUserId) {
        adminUserService.revokeAdmin(userId, actingUserId);
        return ResponseEntity.noContent().build();
    }
}
