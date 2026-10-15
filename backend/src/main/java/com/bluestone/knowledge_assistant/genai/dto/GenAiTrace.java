package com.bluestone.knowledge_assistant.genai.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

/**
 * The diagnosable half of an answer. A deliberate SUBSET of what the service sends.
 *
 * <p>{@code @JsonIgnoreProperties(ignoreUnknown = true)} is intentional and is the asymmetry
 * that makes this boundary safe to extend: the REQUEST side forbids unknown fields so Spring
 * sending garbage is loud, while the RESPONSE side tolerates them so Python can add a trace
 * field — as it did twice in two days, {@code collapsed_duplicates} then {@code dropped_quotes} —
 * without breaking this client on deploy.
 *
 * <p>These are logged, never returned to the user: {@code dropped_quotes} can contain fragments
 * of document text, and the log is not a place for document text.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GenAiTrace(
        @JsonProperty("trace_id") String traceId,
        @JsonProperty("candidates_before_threshold") int candidatesBeforeThreshold,
        @JsonProperty("collapsed_duplicates") int collapsedDuplicates,
        @JsonProperty("prompt_template_version") String promptTemplateVersion,
        @JsonProperty("prompt_tokens") int promptTokens,
        @JsonProperty("completion_tokens") int completionTokens,
        @JsonProperty("generate_ms") int generateMs,
        @JsonProperty("total_ms") int totalMs,
        @JsonProperty("dropped_quotes") List<String> droppedQuotes,
        /**
         * The capability the service was asked for and does not have, or null.
         *
         * <p>"send messages", "browse the web", "reveal its prompt". Spring turns this into
         * a sentence naming the limitation, because "I couldn't find anything in your
         * documents" would be a false explanation for a request the service simply cannot
         * serve — the documents are not the reason.
         */
        @JsonProperty("unsupported_request") String unsupportedRequest,

        /**
         * When NOTHING cleared the relevance floor, the best score that failed it.
         *
         * <p>Separates a near miss from a question the corpus has never heard of, which the
         * user previously could not tell apart: both produced "I couldn't find anything in
         * your documents… upload a document that covers it".
         *
         * <p>Measured on the real corpus: <em>"tell me about ai saftey"</em> scores 0.5355
         * against a 0.60 floor while the correct spelling scores 0.7120. The document was
         * there the whole time, and advising an upload was advice about the wrong problem.
         *
         * <p>Null when something WAS admitted, and null when the query matched no rows at
         * all — being near nothing is different from being near a miss.
         */
        @JsonProperty("best_rejected_score") Double bestRejectedScore,

        /** The floor that score failed, so the message can quote both without assuming it. */
        @JsonProperty("min_score") Double minScore,

        /**
         * Words corrected before the search that produced this answer.
         *
         * <p>Non-empty only when the question AS TYPED retrieved nothing and the corrected
         * one retrieved something. Shown to the user so they are told what was assumed
         * rather than silently answered about a different word — "ai saftey" is a typo the
         * embedding model cannot see through, and answering it as "ai safety" without
         * saying so would be a quiet substitution of their question.
         */
        @JsonProperty("spelling_corrections") List<SpellingCorrection> spellingCorrections
) {
    /** One word replaced: what was typed, and what it was searched as. */
    public record SpellingCorrection(
            @JsonProperty("typed") String typed,
            @JsonProperty("used") String used) {}
}
