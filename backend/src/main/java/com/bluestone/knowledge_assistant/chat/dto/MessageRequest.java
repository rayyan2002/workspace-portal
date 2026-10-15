package com.bluestone.knowledge_assistant.chat.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.UUID;

public record MessageRequest(
        @NotNull(message = "Session ID is required")
        UUID sessionId,

        // messages.content is TEXT, i.e. unbounded — so the cap has to come from here,
        // otherwise a multi-megabyte body is a perfectly valid message.
        @NotBlank(message = "Message content cannot be blank")
        @Size(max = 4000, message = "Message content must be at most 4000 characters")
        String content,

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