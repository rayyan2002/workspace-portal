package com.bluestone.knowledge_assistant.genai.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;

/**
 * One tool proposal as the GenAI service emits it. Day 14b: this was {@code List<Object>}.
 *
 * <p><strong>{@code arguments} is deliberately an untyped map, and that is not laziness.</strong>
 * The service publishes a discriminated union on {@code tool}, so the obvious move is
 * {@code @JsonTypeInfo} with a sealed interface and three subtypes. It was rejected because
 * of WHERE IT FAILS: Jackson would throw while deserialising the whole response, so one
 * unrecognised proposal would cost the user their ANSWER. A proposal is a suggestion; an
 * answer is the product.
 *
 * <p>So the shape is validated one level up, by {@link
 * com.bluestone.knowledge_assistant.chat.ActionProposer}, which drops a proposal it cannot
 * translate and keeps the answer. Fails closed at the right granularity. The map is never
 * passed through to the frontend — every field the UI sees is one the translator rebuilt.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GenAiProposal(
        @JsonProperty("arguments") Map<String, Object> arguments,
        @JsonProperty("label") String label
) {}
