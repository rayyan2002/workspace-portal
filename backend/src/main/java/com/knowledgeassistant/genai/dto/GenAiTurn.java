package com.knowledgeassistant.genai.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * One earlier message in the conversation, as the GenAI service expects it.
 *
 * <p>Spring owns the {@code messages} table and sends these. The service stays stateless and
 * {@code session_id} remains correlation-only, never looked up — which keeps rule R1 intact
 * (Python holds SELECT on the chunk tables and nothing else) and keeps an answer reproducible
 * from its request alone.
 *
 * <p>{@code role} is the literal string the contract accepts: {@code "user"} or
 * {@code "assistant"}, lower-case. {@code MessageSender} already spells them that way, so the
 * mapping is {@code name()} and not a translation layer.
 */
public record GenAiTurn(
        @JsonProperty("role") String role,
        @JsonProperty("content") String content
) {}
