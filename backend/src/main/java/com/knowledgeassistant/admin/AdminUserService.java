package com.knowledgeassistant.admin;

import com.knowledgeassistant.common.AdminRoleChangeException;
import com.knowledgeassistant.common.UserNotFoundException;
import com.knowledgeassistant.user.Role;
import com.knowledgeassistant.user.RoleName;
import com.knowledgeassistant.user.RoleRepository;
import com.knowledgeassistant.user.User;
import com.knowledgeassistant.user.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

/**
 * Granting and revoking ROLE_ADMIN.
 *
 * <p>Both operations are audited to the log with WHO performed them, because "who made this
 * person an administrator?" is the same class of question as "who told the AI to create this
 * task" — and the action audit trail answers that one.
 */
@Service
public class AdminUserService {

    private static final Logger log = LoggerFactory.getLogger(AdminUserService.class);

    private final UserRepository userRepository;
    private final RoleRepository roleRepository;

    public AdminUserService(UserRepository userRepository, RoleRepository roleRepository) {
        this.userRepository = userRepository;
        this.roleRepository = roleRepository;
    }

    @Transactional
    public void grantAdmin(UUID targetId, UUID actingUserId) {
        User target = load(targetId);
        if (isAdmin(target)) {
            return;                       // already an admin; granting twice is not an error
        }
        Role admin = roleRepository.findByName(RoleName.ROLE_ADMIN)
                .orElseThrow(() -> new IllegalStateException(
                        "ROLE_ADMIN is missing from the roles table — V10 did not run"));
        target.addRole(admin);
        userRepository.save(target);
        log.info("admin.granted targetId={} targetEmail={} byUserId={}",
                targetId, target.getEmail(), actingUserId);
    }

    @Transactional
    public void revokeAdmin(UUID targetId, UUID actingUserId) {
        User target = load(targetId);
        if (!isAdmin(target)) {
            return;                       // not an admin; revoking twice is not an error
        }

        // YOU CANNOT REMOVE YOUR OWN ADMIN RIGHTS. Not paternalism — the endpoint that would
        // put them back is itself behind hasRole('ADMIN'), so a self-demotion is a one-way
        // door out of the only door back in.
        if (targetId.equals(actingUserId)) {
            throw new AdminRoleChangeException(
                    "You cannot remove your own administrator access. Ask another "
                            + "administrator to do it.");
        }

        // AND NEVER THE LAST ONE. Same reasoning one step further out: an application with
        // no administrator cannot appoint one, and recovering means editing the database by
        // hand. Cheaper to refuse than to explain afterwards.
        if (countAdmins() <= 1) {
            throw new AdminRoleChangeException(
                    "This is the only administrator. Promote somebody else first.");
        }

        target.getRoles().removeIf(r -> r.getName() == RoleName.ROLE_ADMIN);
        userRepository.save(target);
        log.info("admin.revoked targetId={} targetEmail={} byUserId={}",
                targetId, target.getEmail(), actingUserId);
    }

    private User load(UUID id) {
        return userRepository.findWithRolesById(id)
                .orElseThrow(() -> new UserNotFoundException("User not found: " + id));
    }

    private boolean isAdmin(User user) {
        return user.getRoles().stream().anyMatch(r -> r.getName() == RoleName.ROLE_ADMIN);
    }

    private long countAdmins() {
        return userRepository.findAll().stream()
                .filter(u -> userRepository.findWithRolesById(u.getId())
                        .map(this::isAdmin).orElse(false))
                .count();
    }
}
