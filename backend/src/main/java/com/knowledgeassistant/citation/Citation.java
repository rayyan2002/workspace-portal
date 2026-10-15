package com.knowledgeassistant.citation;

import com.knowledgeassistant.document.Document;
import jakarta.persistence.*;

import java.time.Instant;
import java.util.UUID;

/**
 * A link from an assistant message back to the document it drew on.
 *
 * <p>The point of the product: an answer you cannot trace to a source is an answer you
 * cannot trust. The table has existed since Day 3; this is the code that finally uses it.
 */
@Entity
@Table(name = "citations")
public class Citation {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", updatable = false, nullable = false)
    private UUID id;

    @Column(name = "message_id", nullable = false)
    private UUID messageId;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "document_id", nullable = false)
    private Document document;

    @Column(name = "section")
    private String section;

    @Column(name = "excerpt", nullable = false)
    private String excerpt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    /** The passage cited. Null once that chunk has been regenerated; the excerpt survives. */
    @Column(name = "chunk_id")
    private UUID chunkId;

    /**
     * Denormalised from the chunk at write time, for the same reason {@code excerpt} is: a
     * citation records what was true WHEN THE ASSISTANT SAID IT, and the chunk may be
     * regenerated or deleted afterwards.
     *
     * <p>Measured: 80 of 177 chunks carry a section and 55 carry a page, and the two are
     * largely complementary — the PDFs that dominate real citations have a page and no
     * heading, which is why a card showing only section rendered nothing for them.
     */
    @Column(name = "page")
    private Integer page;

    /** Retrieval similarity, NOT answer confidence. See V19 and {@code CitationDto.qualityFor}. */
    @Column(name = "score")
    private Float score;

    protected Citation() {}

    public Citation(UUID messageId, Document document, String section, String excerpt, Instant createdAt) {
        this(messageId, document, section, excerpt, createdAt, null, null, null);
    }

    /**
     * The full form, as Month 3 writes them.
     *
     * @param chunkId the passage cited, so "which chunk did the assistant actually use?" is
     *                answerable after the fact. Nullable: a regenerated chunk sets it null
     *                and the excerpt survives.
     * @param page    denormalised from the chunk, because a citation records what was true
     *                when it was made
     * @param score   retrieval similarity, NOT answer confidence
     */
    public Citation(UUID messageId, Document document, String section, String excerpt,
                    Instant createdAt, UUID chunkId, Integer page, Float score) {
        this.messageId = messageId;
        this.document = document;
        this.section = section;
        this.excerpt = excerpt;
        this.createdAt = createdAt;
        this.chunkId = chunkId;
        this.page = page;
        this.score = score;
    }

    public UUID getId() { return id; }
    public UUID getMessageId() { return messageId; }
    public Document getDocument() { return document; }
    public String getSection() { return section; }
    public String getExcerpt() { return excerpt; }
    public Instant getCreatedAt() { return createdAt; }
    public UUID getChunkId() { return chunkId; }
    public Integer getPage() { return page; }
    public Float getScore() { return score; }
}
