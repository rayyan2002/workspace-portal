package com.bluestone.knowledge_assistant.auth.dto;
import jakarta.validation.constraints.NotBlank;
public record LoginRequest(@NotBlank String email, @NotBlank String password) {

    /**
     * A record's generated toString() prints every component, so any log line or
     * exception message that interpolates this object would print the password.
     * Overriding it makes the leak impossible instead of merely discouraged.
     */
    @Override
    public String toString() {
        return "LoginRequest[email=" + email + ", password=***]";
    }
}
