package com.knowledgeassistant.admin;

import com.knowledgeassistant.auth.dto.UserDto;
import com.knowledgeassistant.common.PageRequestFactory;
import com.knowledgeassistant.common.dto.PageResponse;
import com.knowledgeassistant.user.UserRepository;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

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

    public AdminController(UserRepository userRepository) {
        this.userRepository = userRepository;
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
    public ResponseEntity<PageResponse<UserDto>> listUsers(
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size) {

        return ResponseEntity.ok(PageResponse.from(
                userRepository.findAll(PageRequestFactory.of(page, size)),
                user -> new UserDto(user.getId(), user.getEmail(), user.getName())));
    }
}
