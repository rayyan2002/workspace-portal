package com.knowledgeassistant.action;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum ActionType {
    CREATE_TASK("create-task"),
    SUMMARIZE_DOCUMENT("summarize-document"),
    LOOKUP_KNOWLEDGE("lookup-knowledge");

    private final String value;

    ActionType(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }

    // Tells Jackson how to deserialize the incoming JSON string back into the Enum
    @JsonCreator
    public static ActionType fromValue(String value) {
        for (ActionType type : values()) {
            if (type.value.equals(value)) {
                return type;
            }
        }
        throw new IllegalArgumentException("Unknown ActionType: " + value);
    }
}