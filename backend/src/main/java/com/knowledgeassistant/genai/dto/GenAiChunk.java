package com.knowledgeassistant.genai.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

/**
 * One chunk as the GenAI service computed it. Every field maps to a {@code document_chunks}
 * column, because Spring writes this row.
 *
 * @param ordinal   1-based within the document. {@code uq_chunk_document_ordinal} and
 *                  {@code chk_chunk_ordinal} both depend on it, and a citation resolves to it.
 * @param charStart offsets index into the EXTRACTED text, not into the original file — for a
 *                  PDF those differ entirely. Stored so a citation can be located again.
 * @param section   heading or sheet name; null for most PDFs.
 * @param page      page number; null for unpaged formats. Measured on the real corpus, these
 *                  two are largely COMPLEMENTARY — 80 of 177 chunks have a section and 55 a
 *                  page — which is why a citation card showing only one rendered blank.
 * @param embedding exactly {@code embedding_dim} floats, unit-normalised at write time so
 *                  cosine similarity IS the dot product and retrieval can use {@code <#>}.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GenAiChunk(
        @JsonProperty("ordinal") int ordinal,
        @JsonProperty("text") String text,
        @JsonProperty("token_count") int tokenCount,
        @JsonProperty("char_start") int charStart,
        @JsonProperty("char_end") int charEnd,
        @JsonProperty("section") String section,
        @JsonProperty("page") Integer page,
        @JsonProperty("embedding") List<Double> embedding
) {}
