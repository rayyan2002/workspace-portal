package com.knowledgeassistant.genai.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/** Where the time went. Logged, never shown to a user. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GenAiIngestTrace(
        @JsonProperty("trace_id") String traceId,
        @JsonProperty("extract_ms") int extractMs,
        @JsonProperty("chunk_ms") int chunkMs,
        @JsonProperty("embed_ms") int embedMs,
        @JsonProperty("total_ms") int totalMs
) {}
