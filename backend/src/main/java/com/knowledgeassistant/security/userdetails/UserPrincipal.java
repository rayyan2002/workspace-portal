package com.knowledgeassistant.security.userdetails;

import com.knowledgeassistant.user.Role;
import com.knowledgeassistant.user.User;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import java.util.Collection;
import java.util.List;
import java.util.Set;
import java.util.UUID;

/**
 * The authenticated principal placed in the {@code SecurityContext}.
 *
 * <p>Deliberately a detached snapshot rather than the JPA entity: it is built once per
 * request from claims or a lookup and must not drag a persistence context or a lazy
 * collection into the security layer. The {@code id} accessor is what
 * {@code @CurrentUserId} reads via its SpEL expression.
 */
public class UserPrincipal implements UserDetails {

    private final UUID id;
    private final String email;
    private final String password;
    private final List<GrantedAuthority> authorities;

    public UserPrincipal(UUID id, String email, String password, Collection<? extends GrantedAuthority> authorities) {
        this.id = id;
        this.email = email;
        this.password = password;
        this.authorities = List.copyOf(authorities);
    }

    /** Builds a principal from a persisted user, including its roles. */
    public static UserPrincipal from(User user) {
        Set<Role> roles = user.getRoles();
        List<GrantedAuthority> authorities = roles.stream()
                .map(role -> (GrantedAuthority) new SimpleGrantedAuthority(role.getName().name()))
                .toList();

        return new UserPrincipal(user.getId(), user.getEmail(), user.getPassword(), authorities);
    }

    /** Builds a principal from verified JWT claims — no database round-trip. */
    public static UserPrincipal fromClaims(UUID id, String email, List<String> roles) {
        List<GrantedAuthority> authorities = roles.stream()
                .map(role -> (GrantedAuthority) new SimpleGrantedAuthority(role))
                .toList();

        return new UserPrincipal(id, email, null, authorities);
    }

    public UUID getId() {
        return id;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return password;
    }

    /** Spring Security's notion of "username"; email is our natural login identifier. */
    @Override
    public String getUsername() {
        return email;
    }
}
