package com.bluestone.knowledge_assistant.genai.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

/**
 * The response from {@code POST /answer}.
 *
 * @param outcome   {@code grounded} or {@code insufficient_context}. Decided by RETRIEVAL
 *                  scores before the model is called, never by the model itself — so it is
 *                  a fact about the corpus, not an opinion.
 * @param answer    empty string when the outcome is {@code insufficient_context}. Spring
 *                  turns that into a sentence a person can read; an empty chat bubble is not
 *                  "a clear insufficient-context response".
 * @param proposals tool proposals, decided by the service from the USER'S MESSAGE ALONE —
 *                  never from retrieved text, so a poisoned document cannot forge a tool
 *                  call. Empty until Day 14b, when routing moved out of this service: Spring
 *                  kept a keyword trigger list in {@code ChatSessionService} and the GenAI
 *                  service held the encoder, so only one of them could run a classifier,
 *                  and only one of them could own the rules without a second copy.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GenAiAnswerResponse(
        @JsonProperty("outcome") String outcome,
        @JsonProperty("answer") String answer,
        @JsonProperty("citations") List<GenAiCitation> citations,
        @JsonProperty("proposals") List<GenAiProposal> proposals,
        @JsonProperty("trace") GenAiTrace trace
) {
    public static final String INSUFFICIENT_CONTEXT = "insufficient_context";

    public boolean isInsufficientContext() {
        return INSUFFICIENT_CONTEXT.equals(outcome);
    }
}
