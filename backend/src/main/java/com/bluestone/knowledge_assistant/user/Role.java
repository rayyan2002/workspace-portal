package com.bluestone.knowledge_assistant.user;

import jakarta.persistence.*;

import java.util.UUID;

@Entity
@Table(name = "roles")
public class Role {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", updatable = false, nullable = false)
    private UUID id;

    @Enumerated(EnumType.STRING)
    @Column(name = "name", nullable = false, unique = true)
    private RoleName name;

    protected Role() {}

    public Role(RoleName name) {
        this.name = name;
    }

    public UUID getId() { return id; }

    public RoleName getName() { return name; }
}
