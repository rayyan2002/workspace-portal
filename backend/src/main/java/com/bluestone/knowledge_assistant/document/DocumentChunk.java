package com.bluestone.knowledge_assistant.document;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.util.UUID;

/**
 * A chunk of a document, as stored by {@code V18__create_document_chunks.sql}.
 *
 * <p><strong>Read-only from Java, and mapped only far enough to hydrate a citation.</strong>
 * The GenAI service returns a {@code chunk_id} and nothing else about the passage — no text —
 * because Spring wrote these rows and should read them from its own database rather than
 * trust a service to echo them back. This entity is how it does that.
 *
 * <p>The {@code embedding vector(384)} column is <em>deliberately not mapped</em>. Hibernate
 * has no type for pgvector, Java has no use for the vector, and mapping it would pull 384
 * floats per citation across the wire to be discarded. {@code ddl-auto=validate} only checks
 * that mapped columns exist, so omitting it is safe — Flyway owns this schema, as it owns
 * every other.
 *
 * <p>Writes stay in Python's half of the boundary... which is the one place rule R1 is
 * inverted: Python holds SELECT only, and these rows are written by {@code benchmarks/11},
 * a fixture loader that documents its own violation. When {@code POST /ingest} lands, Spring
 * writes them.
 */
@Entity
@Table(name = "document_chunks")
public class DocumentChunk {

    @Id
    private UUID id;

    @Column(name = "document_id", nullable = false)
    private UUID documentId;

    /** 1-based within its document. Contract revision 9 corrected the published floor to match. */
    @Column(nullable = false)
    private int ordinal;

    @Column(nullable = false)
    private String text;

    /** Heading, sheet name, or null. Becomes {@code CitationDto.section}. */
    @Column
    private String section;

    /**
     * Page number for paged formats, or null.
     *
     * <p>Measured on the real corpus: 80 of 177 chunks have a section and 55 have a page,
     * and the two are largely COMPLEMENTARY — the PDFs that dominate real citations carry a
     * page and no heading, which is why a card showing only section rendered nothing at all
     * for them.
     */
    @Column
    private Integer page;

    protected DocumentChunk() {
        // JPA
    }

    public UUID getId() { return id; }
    public UUID getDocumentId() { return documentId; }
    public int getOrdinal() { return ordinal; }
    public String getText() { return text; }
    public String getSection() { return section; }
    public Integer getPage() { return page; }
}
