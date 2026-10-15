package com.bluestone.knowledge_assistant.document;

import com.bluestone.knowledge_assistant.genai.dto.GenAiChunk;
import com.bluestone.knowledge_assistant.genai.dto.GenAiIngestResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.sql.PreparedStatement;
import java.sql.Types;
import java.util.List;
import java.util.StringJoiner;
import java.util.UUID;

/**
 * Writes the chunks the GenAI service computed. Day 16 — the first time Spring has done this.
 *
 * <p><strong>JDBC rather than JPA, and that is forced rather than chosen.</strong> The
 * {@code embedding} column is pgvector's {@code vector(384)}, a PostgreSQL extension type
 * Hibernate has no mapping for. {@link DocumentChunk} is deliberately a READ-only entity with
 * no setters — it exists so retrieval can hydrate citation excerpts, and it does not even
 * declare the vector column. Adding a custom Hibernate type to write one column would be more
 * machinery than the batch insert below.
 *
 * <p><strong>The vector is sent as text and cast.</strong> {@code ?::vector} is pgvector's
 * own input format, and it is not a Python list literal by coincidence — no spaces, square
 * brackets, plain decimals. Driver-side array binding does not work here because the target
 * is an extension type, not {@code float8[]}.
 *
 * <p><strong>ONE TRANSACTION FOR THE WHOLE DOCUMENT.</strong> This is the property the whole
 * day rests on: a half-written document must never become retrievable. The caller sets
 * {@code ready} only after this returns, so the ordering is "all chunks committed, then
 * searchable" — never the reverse, and never partially. {@code uq_chunk_document_ordinal}
 * makes a double write fail loudly rather than silently doubling a document's chunks.
 */
@Component
public class DocumentChunkWriter {

    private static final Logger log = LoggerFactory.getLogger(DocumentChunkWriter.class);

    private static final String INSERT = """
            INSERT INTO document_chunks
                (id, document_id, ordinal, text, token_count, char_start, char_end,
                 section, page, embedding, embedding_model, embedding_model_revision, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?::vector, ?, ?, now())
            """;

    /** Batched rather than one statement per chunk: a 180-chunk document is 180 round trips. */
    private static final int BATCH_SIZE = 100;

    private final JdbcTemplate jdbcTemplate;

    public DocumentChunkWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    /**
     * Replaces this document's chunks with the ones just computed.
     *
     * <p><strong>Deletes first, and that makes re-ingestion safe.</strong> Chunks are derived
     * data — embedding is deterministic, so the same bytes and the same pinned model produce
     * the same vectors — and {@code ON DELETE CASCADE} plus
     * {@code uq_chunk_document_ordinal} were both written on the assumption that they are
     * regenerable. Without the delete, re-ingesting a document would hit the unique
     * constraint on ordinal 1 and fail; with it, re-ingestion is idempotent, which is what
     * makes a failed upload recoverable by re-uploading.
     *
     * @return the number of chunks written
     */
    @Transactional
    public int write(UUID documentId, GenAiIngestResponse ingested, int expectedDimension) {
        List<GenAiChunk> chunks = ingested.chunks();
        if (chunks == null || chunks.isEmpty()) {
            // Not an exception: the caller decides what an empty document means, and it has
            // more context. This method's job is to write what it was given.
            return 0;
        }
        if (ingested.embeddingDim() != expectedDimension) {
            // Checked BEFORE any insert. Postgres would reject row 1 with a cast error that
            // names neither number, and the document would be left half-processed.
            throw new IllegalStateException(
                    "The GenAI service returned " + ingested.embeddingDim()
                            + "-dimensional vectors, but document_chunks.embedding is vector("
                            + expectedDimension + "). The embedding model and the schema disagree.");
        }

        int removed = jdbcTemplate.update("DELETE FROM document_chunks WHERE document_id = ?", documentId);
        if (removed > 0) {
            log.info("document.chunks.replaced documentId={} removed={}", documentId, removed);
        }

        for (int from = 0; from < chunks.size(); from += BATCH_SIZE) {
            List<GenAiChunk> batch = chunks.subList(from, Math.min(from + BATCH_SIZE, chunks.size()));
            jdbcTemplate.batchUpdate(INSERT, batch, batch.size(), (PreparedStatement ps, GenAiChunk c) -> {
                ps.setObject(1, UUID.randomUUID());
                ps.setObject(2, documentId);
                ps.setInt(3, c.ordinal());
                ps.setString(4, c.text());
                ps.setInt(5, c.tokenCount());
                ps.setInt(6, c.charStart());
                ps.setInt(7, c.charEnd());
                ps.setString(8, c.section());
                if (c.page() == null) {
                    ps.setNull(9, Types.INTEGER);
                } else {
                    ps.setInt(9, c.page());
                }
                ps.setString(10, vectorLiteral(c.embedding()));
                // The model's identity travels with every vector. Without it, re-embedding
                // with a different model leaves two vector SPACES in one column and
                // similarity search silently returns nonsense; with it, rows from the old
                // space are simply invisible to the new query.
                ps.setString(11, ingested.embeddingModel());
                ps.setString(12, ingested.embeddingModelRevision());
            });
        }

        log.info("document.chunks.written documentId={} chunks={} model={} revision={}",
                documentId, chunks.size(), ingested.embeddingModel(),
                ingested.embeddingModelRevision());
        return chunks.size();
    }

    /**
     * pgvector's text input format: {@code [1.0,-0.5,0.25]}.
     *
     * <p>No spaces, and not {@code List.toString()} — which produces {@code [1.0, -0.5]} with
     * spaces after the commas. pgvector tolerates that today, and relying on it would be
     * relying on a parser's leniency rather than on its documented format.
     */
    static String vectorLiteral(List<Double> values) {
        StringJoiner joiner = new StringJoiner(",", "[", "]");
        for (Double value : values) {
            joiner.add(Double.toString(value));
        }
        return joiner.toString();
    }
}
