package com.knowledgeassistant.user;

import org.springframework.data.repository.query.Param;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface UserRepository extends JpaRepository<User, UUID> {

    /**
     * Roles are fetched eagerly here specifically because authentication happens outside
     * any open persistence context — a LAZY collection would blow up on access when the
     * JWT filter builds the principal.
     */
    @EntityGraph(attributePaths = "roles")
    Optional<User> findByEmail(String email);

    @EntityGraph(attributePaths = "roles")
    Optional<User> findWithRolesById(UUID id);

    /**
     * The ids of every user holding a role, in ONE query.
     *
     * <p>The administration list needs to know who is already an administrator. Asking per
     * user would be the N+1 that QueryCountTest exists to catch, and the list is paged, so
     * the cost would grow with the page size.
     */
    @Query("select u.id from User u join u.roles r where r.name = :name")
    java.util.Set<UUID> findIdsByRoleName(@Param("name") RoleName name);
}
