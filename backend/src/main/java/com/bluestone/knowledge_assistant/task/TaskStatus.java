package com.bluestone.knowledge_assistant.task;

import com.fasterxml.jackson.annotation.JsonValue;

public enum TaskStatus {
    todo("todo"),
    in_progress("in-progress"),
    done("done");

    private final String value;

    TaskStatus(String value) {
        this.value = value;
    }

    // Single source of truth for JSON serialization (Frontend)
    @JsonValue
    public String getValue() {
        return value;
    }

    // Single source of truth for DB deserialization (PostgreSQL)
    public static TaskStatus fromValue(String value) {
        for (TaskStatus s : values()) {
            if (s.value.equals(value)) {
                return s;
            }
        }
        throw new IllegalArgumentException("Unknown status: " + value);
    }
}