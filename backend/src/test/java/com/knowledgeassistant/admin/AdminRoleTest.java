package com.knowledgeassistant.admin;

import com.knowledgeassistant.common.AdminRoleChangeException;
import com.knowledgeassistant.common.UserNotFoundException;
import com.knowledgeassistant.support.TestFixtures;
import com.knowledgeassistant.user.RoleName;
import com.knowledgeassistant.user.User;
import com.knowledgeassistant.user.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * An administrator can appoint another — and cannot lock everybody out doing it.
 *
 * <p>Both refusals guard the same one-way door: the endpoint that would undo the mistake is
 * itself behind hasRole('ADMIN'), so an application with no administrator cannot appoint one
 * and recovery means editing the database by hand.
 */
@SpringBootTest
@ActiveProfiles("test")
@Transactional
class AdminRoleTest {

    @Autowired private AdminUserService adminUserService;
    @Autowired private UserRepository userRepository;
    @Autowired private TestFixtures fixtures;

    private boolean isAdmin(User user) {
        return userRepository.findWithRolesById(user.getId()).orElseThrow()
                .getRoles().stream().anyMatch(r -> r.getName() == RoleName.ROLE_ADMIN);
    }

    @Test
    void anAdminCanPromoteAnOrdinaryUser() {
        User admin = fixtures.user("boss@example.com", "securepassword123",
                RoleName.ROLE_USER, RoleName.ROLE_ADMIN);
        User ordinary = fixtures.user("new@example.com", "securepassword123",
                RoleName.ROLE_USER);
        assertFalse(isAdmin(ordinary));

        adminUserService.grantAdmin(ordinary.getId(), admin.getId());

        assertTrue(isAdmin(ordinary), "the promoted user must hold ROLE_ADMIN");
    }

    @Test
    void promotingTwiceIsNotAnError() {
        // PUT, not POST: a double-clicked button must not mean something different from a
        // single click.
        User admin = fixtures.user("boss2@example.com", "securepassword123",
                RoleName.ROLE_USER, RoleName.ROLE_ADMIN);
        User ordinary = fixtures.user("new2@example.com", "securepassword123",
                RoleName.ROLE_USER);

        adminUserService.grantAdmin(ordinary.getId(), admin.getId());
        adminUserService.grantAdmin(ordinary.getId(), admin.getId());

        assertTrue(isAdmin(ordinary));
    }

    @Test
    void anAdminCannotRemoveTheirOwnAccess() {
        User admin = fixtures.user("boss3@example.com", "securepassword123",
                RoleName.ROLE_USER, RoleName.ROLE_ADMIN);
        fixtures.user("other3@example.com", "securepassword123",
                RoleName.ROLE_USER, RoleName.ROLE_ADMIN);

        AdminRoleChangeException refused = assertThrows(AdminRoleChangeException.class,
                () -> adminUserService.revokeAdmin(admin.getId(), admin.getId()));

        assertTrue(refused.getMessage().contains("your own"));
        assertTrue(isAdmin(admin), "the refusal must leave the role in place");
    }

    @Test
    void theLastAdminCannotBeDemoted() {
        // STRIPPED FIRST, because this suite shares a database with the running application
        // and that database already has an administrator. Without this the user created
        // below is never actually the last one and the guard correctly does not fire — the
        // test would pass or fail depending on who happens to be in the database, which is
        // no test at all. @Transactional rolls the stripping back.
        for (User existing : userRepository.findAll()) {
            User withRoles = userRepository.findWithRolesById(existing.getId()).orElseThrow();
            if (withRoles.getRoles().removeIf(r -> r.getName() == RoleName.ROLE_ADMIN)) {
                userRepository.save(withRoles);
            }
        }

        User onlyAdmin = fixtures.user("solo@example.com", "securepassword123",
                RoleName.ROLE_USER, RoleName.ROLE_ADMIN);
        User other = fixtures.user("bystander@example.com", "securepassword123",
                RoleName.ROLE_USER);

        AdminRoleChangeException refused = assertThrows(AdminRoleChangeException.class,
                () -> adminUserService.revokeAdmin(onlyAdmin.getId(), other.getId()));

        assertTrue(refused.getMessage().contains("only administrator"));
        assertTrue(isAdmin(onlyAdmin));
    }

    @Test
    void anAdminCanBeDemotedWhileAnotherRemains() {
        User keeper = fixtures.user("keeper@example.com", "securepassword123",
                RoleName.ROLE_USER, RoleName.ROLE_ADMIN);
        User leaving = fixtures.user("leaving@example.com", "securepassword123",
                RoleName.ROLE_USER, RoleName.ROLE_ADMIN);

        adminUserService.revokeAdmin(leaving.getId(), keeper.getId());

        assertFalse(isAdmin(leaving));
        assertTrue(isAdmin(keeper));
    }

    @Test
    void anUnknownUserIsNotFound() {
        User admin = fixtures.user("boss4@example.com", "securepassword123",
                RoleName.ROLE_USER, RoleName.ROLE_ADMIN);

        assertThrows(UserNotFoundException.class,
                () -> adminUserService.grantAdmin(UUID.randomUUID(), admin.getId()));
    }
}
