package com.bluestone.knowledge_assistant.citation;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.Collection;
import java.util.List;
import java.util.UUID;

@Repository
public interface CitationRepository extends JpaRepository<Citation, UUID> {

    /**
     * Loads citations for a whole page of messages in one query.
     *
     * <p>Fetching per message would be a classic N+1 across a conversation. The document
     * is fetched eagerly because the DTO needs its filename and the mapping happens
     * outside any open session.
     */
    @EntityGraph(attributePaths = "document")
    List<Citation> findByMessageIdInOrderByCreatedAtAsc(Collection<UUID> messageIds);

    /**
     * Which conversations would be destroyed by deleting this document, and how much is in them.
     *
     * <p><strong>Native, because the join does not exist in the object model.</strong>
     * {@code Citation.messageId} and {@code Message.sessionId} are raw UUID columns rather than
     * {@code @ManyToOne} relations — a deliberate choice recorded in those entities to avoid
     * lazy-loading a whole conversation to render one citation card. The cost is that
     * citation → message → session cannot be expressed in JPQL, so it is written in SQL here
     * rather than by adding mappings that exist only to serve one query.
     *
     * <p>{@code otherDocuments} is the field that makes the confirmation honest. A chat is not
     * necessarily <em>about</em> the document being deleted: measured on the live corpus, a
     * ten-message conversation titled "tell me about finance" cites four different documents,
     * and deleting any one of them would take the whole thing. Showing only a title would hide
     * that; showing the count lets a person see what they are actually about to lose.
     *
     * <p>Scoped by {@code user_id} as well as document: a caller may only ever learn about
     * their own conversations.
     */
    @Query(value = """
            SELECT s.id              AS sessionId,
                   s.title           AS title,
                   (SELECT count(*) FROM messages m2 WHERE m2.session_id = s.id) AS messageCount,
                   (SELECT count(DISTINCT c2.document_id)
                      FROM citations c2
                      JOIN messages m3 ON m3.id = c2.message_id
                     WHERE m3.session_id = s.id
                       AND c2.document_id <> :documentId)                        AS otherDocuments
            FROM citations c
            JOIN messages m       ON m.id = c.message_id
            JOIN chat_sessions s  ON s.id = m.session_id
            WHERE c.document_id = :documentId
              AND s.user_id = :ownerId
            GROUP BY s.id, s.title, s.updated_at
            ORDER BY s.updated_at DESC
            """, nativeQuery = true)
    List<AffectedChat> findChatsCiting(@Param("documentId") UUID documentId,
                                       @Param("ownerId") UUID ownerId);

    /**
     * The OTHER documents each affected conversation draws on, named rather than counted.
     *
     * <p>A second query rather than a join onto the first: one conversation can cite many
     * documents, so folding them into the per-chat row would multiply it and make the message
     * counts wrong. Two small queries assembled in the service is the honest shape.
     *
     * <p>These documents are <strong>not</strong> deleted — only the conversations are. Naming
     * them lets the dialog say which other material the user is losing the discussion of, and
     * link to it so they can go and read it instead.
     */
    @Query(value = """
            SELECT DISTINCT m.session_id AS sessionId,
                            d.id         AS documentId,
                            d.filename   AS filename
            FROM citations c
            JOIN messages m      ON m.id = c.message_id
            JOIN chat_sessions s ON s.id = m.session_id
            JOIN documents d     ON d.id = c.document_id
            WHERE s.user_id = :ownerId
              AND c.document_id <> :documentId
              AND m.session_id IN (
                  SELECT m2.session_id
                  FROM citations c2
                  JOIN messages m2 ON m2.id = c2.message_id
                  WHERE c2.document_id = :documentId)
            ORDER BY d.filename
            """, nativeQuery = true)
    List<OtherDocument> findOtherDocumentsInChatsCiting(@Param("documentId") UUID documentId,
                                                        @Param("ownerId") UUID ownerId);

    /** One other document referenced by an affected conversation. */
    interface OtherDocument {
        UUID getSessionId();
        UUID getDocumentId();
        String getFilename();
    }

    /** A projection, so the query returns what the DTO needs and nothing else. */
    interface AffectedChat {
        UUID getSessionId();
        String getTitle();
        long getMessageCount();
        long getOtherDocuments();
    }
}
