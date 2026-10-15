package com.bluestone.knowledge_assistant.document;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Collection;
import java.util.List;
import java.util.UUID;

/**
 * Reads chunk rows so a citation can carry the passage it actually cites.
 *
 * <p>{@code findByIdIn} rather than a loop of {@code findById}: an answer cites up to
 * {@code top_k} chunks, and one query for five ids beats five queries for one.
 */
public interface DocumentChunkRepository extends JpaRepository<DocumentChunk, UUID> {

    List<DocumentChunk> findByIdIn(Collection<UUID> ids);
}
