package com.knowledgeassistant.genai.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.UUID;

/**
 * The response from {@code POST /ingest}: chunks and their vectors, computed but NOT stored.
 *
 * <p>Day 16. The GenAI service holds {@code SELECT} on the chunk tables and writes nothing —
 * rule R1 — so it returns rows and Spring inserts them. That boundary costs a few hundred
 * kilobytes on the wire for a large document and buys a single owner of the schema.
 *
 * @param chunkCount    the service's own count. Compared against {@code chunks.size()} on
 *                      arrival, because a truncated response would otherwise be written as a
 *                      short but complete-looking document.
 * @param embeddingDim  checked against the {@code vector(384)} column before any insert is
 *                      attempted. A mismatch here is a misconfigured model, and the useful
 *                      place to say so is before Postgres raises a cast error on row 1.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GenAiIngestResponse(
        @JsonProperty("document_id") UUID documentId,
        @JsonProperty("chunk_count") int chunkCount,
        @JsonProperty("embedding_model") String embeddingModel,
        @JsonProperty("embedding_model_revision") String embeddingModelRevision,
        @JsonProperty("embedding_dim") int embeddingDim,
        @JsonProperty("chunks") List<GenAiChunk> chunks,
        @JsonProperty("trace") GenAiIngestTrace trace
) {}
