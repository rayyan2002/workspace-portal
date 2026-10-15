package com.bluestone.knowledge_assistant.document;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface DocumentRepository extends JpaRepository<Document, UUID> {

    // --- Ownership folded into the lookup, as everywhere else -----------------
    // No findById(..) then compare-owner: an unowned document must simply not
    // resolve, so "not yours" and "not there" collapse into the same 404 and the
    // id space stays unenumerable.

    List<Document> findByOwner_IdOrderByUploadDateDesc(UUID ownerId);

    List<Document> findByOwner_IdAndStatusOrderByUploadDateDesc(UUID ownerId, DocumentStatus status);

    // Paged variants. Spring Data issues a second COUNT query for the total, which is
    // the cost of being able to render a pager at all — one extra query per request,
    // not one per row.
    Page<Document> findByOwner_IdOrderByUploadDateDesc(UUID ownerId, Pageable pageable);

    Page<Document> findByOwner_IdAndStatusOrderByUploadDateDesc(UUID ownerId, DocumentStatus status, Pageable pageable);

    /**
     * Filename search, case-insensitive, applied in the DATABASE.
     *
     * Once a list is paged, a client-side filter only searches the page that happens
     * to be loaded — a search box that silently ignores 230 of 250 documents is worse
     * than no search box.
     *
     * The search term is an EMPTY STRING rather than null when absent, and the caller
     * guarantees that. Passing null blew up with "function lower(bytea) does not
     * exist": a null String parameter carries no type over JDBC, so the driver sends
     * it as bytea and LOWER() has no overload for that. An empty term makes the LIKE
     * pattern '%%', which matches every row — same intent, no untyped null.
     *
     * Status stays a nullable enum with an IS NULL guard, which Hibernate types
     * correctly because the parameter is bound from an enum-typed argument.
     */
    @Query("""
            SELECT d FROM Document d
            WHERE d.owner.id = :ownerId
              AND (:status IS NULL OR d.status = :status)
              AND LOWER(d.filename) LIKE LOWER(CONCAT('%', :term, '%'))
            ORDER BY d.uploadDate DESC
            """)
    Page<Document> search(@Param("ownerId") UUID ownerId,
                          @Param("status") DocumentStatus status,
                          @Param("term") String term,
                          Pageable pageable);

    Optional<Document> findByIdAndOwner_Id(UUID id, UUID ownerId);
}
