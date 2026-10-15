package com.bluestone.knowledge_assistant.genai.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.UUID;

/**
 * One citation as the GenAI service reports it: which chunk, from which document, at what score.
 *
 * <p><strong>`quote` is the DOCUMENT's sentence, not the model's.</strong> The service resolves
 * the model's quote to a chunk and returns the sentence from THAT CHUNK which matched. It is a
 * located span of stored text, not generated prose — which is why displaying it is safe. Spring
 * still owns the chunk rows and falls back to the full stored text when the service could not
 * isolate a sentence.
 * No ordinal because contract revision 10 removed it — nothing read it: the {@code citations}
 * table has no such column, {@code CitationDto} has no such field, and neither does the
 * frontend's {@code Citation} type. {@code chunkId} identifies the row on its own.
 */
public record GenAiCitation(
        @JsonProperty("chunk_id") UUID chunkId,
        @JsonProperty("document_id") UUID documentId,
        @JsonProperty("score") double score,
        @JsonProperty("quote") String quote
) {}
