package com.knowledgeassistant.chat.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateSessionRequest(
        @NotBlank(message = "Initial message is required")
        @Size(max = 4000, message = "Initial message must be at most 4000 characters")
        String initialMessage,

        /**
         * Which generation backend answers: "local" or "gemini". Optional — omitted means
         * the service's configured default, which is local.
         *
         * <p><strong>The choice is about where the document text goes.</strong> `local`
         * keeps the retrieved chunks on this machine; `gemini` sends them to Google.
         * Everything else — retrieval, citations, the grounding guard, quarantine — is
         * identical either way, so this is a privacy and quality trade, not a feature flag.
         *
         * <p>Not validated against an enum here on purpose: the GenAI service owns the list
         * of backends and rejects an unknown one with a 422, which is one copy of that list
         * rather than two.
         */
        @Size(max = 20) String model
) {}