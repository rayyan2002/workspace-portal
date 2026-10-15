package com.bluestone.knowledge_assistant.genai.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.UUID;

/**
 * The body of {@code POST /answer}. Field names are snake_case <strong>deliberately and
 * exactly</strong>.
 *
 * <p>Every Pydantic model on that boundary sets {@code extra="forbid"}, so sending
 * {@code allowedDocumentIds} instead of {@code allowed_document_ids} is not quietly ignored —
 * it is a 422 on the first request. That is the intended behaviour on both sides: drift
 * should be loud and immediate rather than a value silently dropped for weeks. The
 * {@code @JsonProperty} annotations are explicit rather than a global naming strategy so
 * the mapping is visible at the field that needs it.
 *
 * @param allowedDocumentIds documents the caller owns AND that are {@code ready}. Required,
 *                           no default, and <strong>an empty list is legal</strong> — it means
 *                           a user with no ready documents and yields
 *                           {@code insufficient_context}. Omitting it is a 422, because
 *                           Spring always knows the answer and omission would be a bug here.
 * @param sessionId          correlation only. Python never looks it up.
 * @param history            earlier turns, oldest first. UNLIKE {@code allowedDocumentIds} this
 *                           may legitimately be empty — the first turn of a conversation has no
 *                           history, and that is not a defect. Capped by
 *                           {@code app.genai.history-turns}: prefill runs at ~280 tokens/s, so
 *                           every turn sent is latency on every request.
 */
@com.fasterxml.jackson.annotation.JsonInclude(
        com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
public record GenAiAnswerRequest(
        @JsonProperty("question") String question,
        @JsonProperty("allowed_document_ids") List<UUID> allowedDocumentIds,
        @JsonProperty("top_k") int topK,
        @JsonProperty("min_score") double minScore,
        @JsonProperty("session_id") UUID sessionId,
        @JsonProperty("history") List<GenAiTurn> history,
        /**
         * "local" or "gemini", or null for the service's default.
         *
         * <p>Jackson omits a null here because the record is serialised with
         * NON_NULL — which matters: the field is optional in the contract, and sending
         * {@code "model": null} to a service with {@code extra="forbid"} would be rejected
         * for a value it never asked for.
         */
        @JsonProperty("model") String model
) {}
