package com.knowledgeassistant.task;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "tasks")
public class Task {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", updatable = false, nullable = false)
    private UUID id;

    @Column(name = "title", nullable = false)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(name = "priority", nullable = false)
    private TaskPriority priority;

    //@Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private TaskStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "completed_at")
    private Instant completedAt;

    @Column(name = "source_session_id", nullable = false)
    private UUID sourceSessionId;

    protected Task() {}

    public Task(String title, TaskPriority priority, TaskStatus status, Instant createdAt, UUID sourceSessionId) {
        this.title = title;
        this.priority = priority;
        this.status = status;
        this.createdAt = createdAt;
        this.sourceSessionId = sourceSessionId;
    }

    // --- Getters ---
    public UUID getId() { return id; }
    public String getTitle() { return title; }
    public TaskPriority getPriority() { return priority; }
    public TaskStatus getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getCompletedAt() { return completedAt; }
    public UUID getSourceSessionId() { return sourceSessionId; }
    public void setStatus(TaskStatus status) {
        this.status = status;
    }

    public void setCompletedAt(java.time.Instant completedAt) {
        this.completedAt = completedAt;
    }
    public java.util.UUID getSessionId() {
        return sourceSessionId; // Use the exact field name declared at the top of your class
    }
}
