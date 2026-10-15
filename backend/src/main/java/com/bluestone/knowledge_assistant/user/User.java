package com.bluestone.knowledge_assistant.user;

import jakarta.persistence.*;

import java.time.Instant;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", updatable = false, nullable = false)
    private UUID id;

    @Column(name = "email", nullable = false, unique = true)
    private String email;

    @Column(name = "password", nullable = false)
    private String password;

    @Column(name = "name")
    private String name;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
            name = "user_roles",
            joinColumns = @JoinColumn(name = "user_id"),
            inverseJoinColumns = @JoinColumn(name = "role_id")
    )
    private Set<Role> roles = new HashSet<>();

    protected User() {}

    public User(String email, String password, String name, Instant createdAt) {
        this.email = email;
        this.password = password;
        this.name = name;
        this.createdAt = createdAt;
    }

    // --- Getters ---
    public UUID getId() { return id; }

    public String getEmail() { return email; }

    public String getPassword() { return password; }

    public String getName() { return name; }

    public Instant getCreatedAt() { return createdAt; }

    public Set<Role> getRoles() { return roles; }

    public void addRole(Role role) { this.roles.add(role); }

    /** Set only with an already-encoded hash — never a plaintext password. */
    public void setPassword(String encodedPassword) { this.password = encodedPassword; }
}
