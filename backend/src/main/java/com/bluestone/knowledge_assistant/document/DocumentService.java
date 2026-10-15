package com.bluestone.knowledge_assistant.document;

import com.bluestone.knowledge_assistant.chat.ChatSessionRepository;
import com.bluestone.knowledge_assistant.citation.CitationRepository;
import com.bluestone.knowledge_assistant.common.DocumentInUseException;
import com.bluestone.knowledge_assistant.common.DocumentNotFoundException;
import com.bluestone.knowledge_assistant.common.DocumentValidationException;
import com.bluestone.knowledge_assistant.common.ErrorCode;
import com.bluestone.knowledge_assistant.genai.GenAiClient;
import com.bluestone.knowledge_assistant.genai.dto.GenAiIngestResponse;
import com.bluestone.knowledge_assistant.common.dto.PageResponse;
import com.bluestone.knowledge_assistant.document.dto.DocumentDeletionImpact;
import com.bluestone.knowledge_assistant.document.dto.DocumentDto;
import com.bluestone.knowledge_assistant.user.User;
import com.bluestone.knowledge_assistant.user.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.PathResource;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class DocumentService {

    private static final Logger log = LoggerFactory.getLogger(DocumentService.class);

    private final DocumentRepository documentRepository;
    private final UserRepository userRepository;

    private static final long MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

    // Strict MIME types
    private static final Set<String> ALLOWED_MIME_TYPES = Set.of(
            "application/pdf",
            "text/plain",
            "text/markdown",
            "text/csv",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document", // DOCX
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" // XLSX
    );

    // Fallback extensions for missing/generic MIME types
    private static final Set<String> ALLOWED_EXTENSIONS = Set.of(
            ".pdf", ".txt", ".md", ".markdown", ".csv", ".docx", ".xlsx"
    );

    private final String uploadDir;
    private final GenAiClient genAiClient;
    private final DocumentChunkWriter chunkWriter;
    private final TransactionTemplate transactionTemplate;
    private final int embeddingDim;
    @jakarta.persistence.PersistenceContext
    private jakarta.persistence.EntityManager entityManager;

    private final CitationRepository citationRepository;
    private final ChatSessionRepository chatSessionRepository;

    public DocumentService(DocumentRepository documentRepository,
                           UserRepository userRepository,
                           GenAiClient genAiClient,
                           DocumentChunkWriter chunkWriter,
                           TransactionTemplate transactionTemplate,
                           @Value("${app.uploads.dir:uploads}") String uploadDir,
                           @Value("${app.genai.embedding-dim:384}") int embeddingDim,
                           CitationRepository citationRepository,
                           ChatSessionRepository chatSessionRepository) {
        this.documentRepository = documentRepository;
        this.userRepository = userRepository;
        this.genAiClient = genAiClient;
        this.chunkWriter = chunkWriter;
        this.transactionTemplate = transactionTemplate;
        this.uploadDir = uploadDir;
        this.embeddingDim = embeddingDim;
        this.citationRepository = citationRepository;
        this.chatSessionRepository = chatSessionRepository;
    }

    /**
     * Stores a document and makes it searchable.
     *
     * <p><strong>Deliberately NOT {@code @Transactional}, and this annotation was removed on
     * Day 16 rather than never added.</strong> Until today this method only touched the
     * database and the disk, so one transaction around it was right. Day 16 added a call to
     * the GenAI service — extraction, chunking and embedding, measured at 236ms for a
     * 2-chunk PDF and 1.5s for a 24-chunk one, and proportionally longer for a large
     * document.
     *
     * <p>A transaction spanning that holds a pooled connection for its whole duration, and
     * HikariCP defaults to ten. This is the identical mistake Day 8 found on the chat path,
     * where it was found the hard way: removing {@code @Transactional} from the METHOD did
     * nothing because the annotation on the CLASS still applied, and 99 tests passed on a
     * boundary that did not exist. This class also carries a class-level
     * {@code @Transactional(readOnly = true)}, so a bare method here would JOIN it — which
     * is why the work below runs through {@link TransactionTemplate} explicitly.
     *
     * <p><strong>Three phases, and the ordering is the product requirement:</strong>
     * <ol>
     *   <li>persist metadata and bytes, status {@code processing} — committed, so a failure
     *       in phase 2 leaves a document the user can see and retry rather than nothing;</li>
     *   <li>call the GenAI service, holding NO connection;</li>
     *   <li>write every chunk in ONE transaction, and only then set {@code ready}.</li>
     * </ol>
     * A half-written document must never be searchable, which is why {@code ready} is set
     * after the chunks are committed and never alongside them.
     */
    public DocumentDto uploadDocument(MultipartFile file, UUID ownerId) {
        // 1. Missing File Check
        if (file == null || file.isEmpty()) {
            log.warn("document.upload_rejected reason=missing_file owner={}", ownerId);
            throw new DocumentValidationException("No file provided.", ErrorCode.MISSING_FILE);
        }

        // 2. Size Check (Backing up the framework property)
        if (file.getSize() > MAX_FILE_SIZE) {
            log.warn("document.upload_rejected reason=too_large owner={} sizeBytes={} limitBytes={}",
                    ownerId, file.getSize(), MAX_FILE_SIZE);
            throw new DocumentValidationException("File exceeds 10MB limit.", ErrorCode.FILE_TOO_LARGE);
        }

        String originalFilename = file.getOriginalFilename();
        if (originalFilename == null || originalFilename.isBlank()) {
            originalFilename = "unknown_file";
        }

        // A filename is attacker-controlled text. It is only ever stored as metadata —
        // the bytes are written under a generated UUID — but strip any directory part
        // anyway so a name like "../../etc/passwd" cannot appear anywhere downstream.
        originalFilename = Paths.get(originalFilename).getFileName().toString();

        // 3. Length Check — documents.filename is VARCHAR(255). Without this, a longer
        //    name reached Postgres and came back as a 500 constraint violation rather
        //    than a 400 the client can act on.
        if (originalFilename.length() > 255) {
            throw new DocumentValidationException("Filename must be at most 255 characters.", ErrorCode.BAD_REQUEST);
        }

        // 4. Type Check (MIME with Extension Fallback)
        String contentType = file.getContentType();
        boolean isValidType = (contentType != null && ALLOWED_MIME_TYPES.contains(contentType));

        if (!isValidType) {
            String lowerCaseName = originalFilename.toLowerCase();
            isValidType = ALLOWED_EXTENSIONS.stream().anyMatch(lowerCaseName::endsWith);
        }

        if (!isValidType) {
            // The filename and declared type are attacker-controlled, so they are
            // logged as values of named keys rather than interpolated into prose —
            // a filename containing a newline cannot then forge a second log line.
            log.warn("document.upload_rejected reason=unsupported_type owner={} contentType={} filename={}",
                    ownerId, contentType, originalFilename);
            throw new DocumentValidationException("Unsupported file type.", ErrorCode.INVALID_FILE_TYPE);
        }

        // PHASE 1 — metadata and bytes, in their own transaction, COMMITTED before the
        //           slow call. If ingestion then fails the user still has a document they
        //           can see and retry, rather than an upload that silently never happened.
        final String filename = originalFilename;
        final String type = contentType;
        Document document = transactionTemplate.execute(status -> {
            // DB First: persist metadata to generate the safe UUID used as the filename.
            // Starts 'pending' because at this instant nothing is on disk yet.
            User owner = userRepository.getReferenceById(ownerId);
            // saveAndFlush, not save. The chunk write in phase 3 is RAW JDBC, so it does not
            // see Hibernate's persistence context — and `save` only queues the INSERT until
            // the next flush. Found by a test: document_chunks_document_id_fkey failed
            // because the chunk insert ran against a documents row that was not in the
            // database yet, even though the Java object existed.
            //
            // In production phase 1 commits before phase 3 begins, so the row is there
            // either way. That makes this a latent dependency on commit ordering rather
            // than a visible bug, which is exactly the kind that survives for weeks and
            // then appears the first time something wraps this call in a transaction.
            Document saved = documentRepository.saveAndFlush(new Document(
                    owner, filename, file.getSize(), Instant.now(), DocumentStatus.pending, type));

            // Save to disk under the UUID (never the user's filename), and RECORD where.
            // Storing the location is what makes the file retrievable later; without it the
            // metadata knew a document existed but not where its bytes were.
            try {
                Path uploadPath = Paths.get(uploadDir).toAbsolutePath().normalize();
                Files.createDirectories(uploadPath);
                Files.copy(file.getInputStream(), uploadPath.resolve(saved.getId().toString()),
                        StandardCopyOption.REPLACE_EXISTING);
                saved.setStoragePath(uploadDir + "/" + saved.getId());
            } catch (IOException e) {
                // Unchecked exception triggers DB rollback, preventing orphan rows.
                throw new RuntimeException(
                        "Failed to store physical file for document " + saved.getId(), e);
            }

            // PROCESSING, not ready — and the reason is a meaning that changed underneath
            // this line rather than a mistake when it was written.
            //
            // In Month 2 `ready` meant listable, previewable and downloadable, and the
            // moment the bytes landed it was all three. That was true.
            //
            // It stopped being true on Month 3 Day 6. Retrieval builds
            // `allowed_document_ids` from documents that are owned AND `ready`, so `ready`
            // quietly acquired a second meaning — SEARCHABLE — and an uploaded file has no
            // chunks until ingestion runs.
            //
            // DAY 16 MAKES IT TRANSIENT rather than terminal. It is `processing` for the
            // duration of the ingest call and then becomes `ready` or `failed`. It is still
            // committed in this order, because the ingest call can fail or time out, and a
            // document whose status was never written would be invisible rather than
            // merely unsearchable.
            saved.setStatus(DocumentStatus.processing);
            return saved;
        });

        log.info("document.uploaded documentId={} owner={} sizeBytes={} contentType={}",
                document.getId(), ownerId, file.getSize(), contentType);

        // PHASES 2 and 3 — the network call and the chunk write. No connection is held
        //                  across the call; see this method's note.
        DocumentStatus outcome = ingest(document.getId(), filename, type);

        // Re-read rather than reuse the detached instance: `ingest` updated the row in its
        // own transaction, and returning a stale `processing` would tell the UI the exact
        // thing this day exists to stop it saying.
        return getDocumentById(document.getId(), ownerId);
    }

    /**
     * Phase 2 and 3: extract, chunk and embed, then write the chunks and publish the status.
     *
     * <p><strong>Never throws.</strong> The upload itself succeeded — the bytes are stored
     * and the row is committed — so a failure here is a document that cannot be searched,
     * not a request that failed. Throwing would return a 5xx for an upload that worked and
     * would leave the user with no document at all; instead the status becomes
     * {@code failed}, which the UI can show and the user can act on by re-uploading.
     *
     * <p><strong>This is what finally produces {@link DocumentStatus#failed}.</strong>
     * BACKLOG.md item 5 recorded that neither {@code processing} nor {@code failed} was ever
     * emitted — a value in an enum that nothing could produce. Both are now reachable.
     *
     * @return the status the document ended in
     */
    private DocumentStatus ingest(UUID documentId, String filename, String contentType) {
        Path path = Paths.get(uploadDir).toAbsolutePath().normalize().resolve(documentId.toString());
        try {
            GenAiIngestResponse ingested =
                    genAiClient.ingest(documentId, filename, contentType, new PathResource(path));

            // ONE transaction for every chunk, and only then `ready`. A half-written
            // document must never be retrievable — `ready` is what puts it into
            // allowed_document_ids, so the ordering here IS the guarantee.
            int written = chunkWriter.write(documentId, ingested, embeddingDim);
            if (written == 0) {
                return publish(documentId, DocumentStatus.failed,
                        "the service returned no chunks");
            }
            return publish(documentId, DocumentStatus.ready, written + " chunks");

        } catch (RuntimeException failure) {
            // Includes GenAiUnavailableException (unreachable, model loading, timeout, or a
            // file the service refused) and anything the chunk write raised.
            log.error("document.ingest.failed documentId={} reason={}",
                    documentId, failure.getMessage());
            return publish(documentId, DocumentStatus.failed, failure.getMessage());
        }
    }

    /** The status transition, in its own short transaction. */
    private DocumentStatus publish(UUID documentId, DocumentStatus status, String why) {
        transactionTemplate.execute(tx -> {
            documentRepository.findById(documentId).ifPresent(d -> d.setStatus(status));
            return null;
        });
        log.info("document.{} documentId={} ({})", status, documentId, why);
        return status;
    }

    @Transactional(readOnly = true)
    public PageResponse<DocumentDto> getDocuments(UUID ownerId, DocumentStatus status, String search, Pageable pageable) {
        // Empty, never null — see DocumentRepository#search for why.
        String term = (search == null) ? "" : search.trim();

        return PageResponse.from(
                documentRepository.search(ownerId, status, term, pageable),
                DocumentDto::from);
    }

    /** Unpaged variant, kept for internal callers that genuinely need every row. */
    @Transactional(readOnly = true)
    public List<DocumentDto> getAllDocuments(UUID ownerId, DocumentStatus status) {
        List<Document> documents = (status != null)
                ? documentRepository.findByOwner_IdAndStatusOrderByUploadDateDesc(ownerId, status)
                : documentRepository.findByOwner_IdOrderByUploadDateDesc(ownerId);

        return documents.stream().map(DocumentDto::from).toList();
    }

    @Transactional(readOnly = true)
    public DocumentDto getDocumentById(UUID id, UUID ownerId) {
        return documentRepository.findByIdAndOwner_Id(id, ownerId)
                .map(DocumentDto::from)
                .orElseThrow(() -> new DocumentNotFoundException("Document not found: " + id));
    }

    /**
     * Resolves a document the caller owns to its bytes on disk.
     *
     * <p>Ownership is checked by the query, so another user's id simply does not
     * resolve — the endpoint cannot be used to fish for documents by id.
     */
    @Transactional(readOnly = true)
    public DownloadableDocument download(UUID id, UUID ownerId) {
        Document document = documentRepository.findByIdAndOwner_Id(id, ownerId)
                .orElseThrow(() -> new DocumentNotFoundException("Document not found: " + id));

        if (document.getStoragePath() == null) {
            throw new DocumentNotFoundException("No file is stored for document: " + id);
        }

        Path root = Paths.get(uploadDir).toAbsolutePath().normalize();
        Path resolved = root.resolve(Paths.get(document.getStoragePath()).getFileName()).normalize();

        // Defence in depth. The stored path is generated by us, not by a user, but
        // reading a file whose location came out of a database row is exactly the shape
        // of a path-traversal bug — so confirm the result is still under the root.
        if (!resolved.startsWith(root)) {
            log.error("Refusing to serve document {}: resolved path {} escapes upload root {}",
                    id, resolved, root);
            throw new DocumentNotFoundException("Document not found: " + id);
        }

        if (!Files.isReadable(resolved)) {
            // ERROR, not WARN. Every other failure in this class is a caller sending
            // something wrong; this one is the system disagreeing with itself — the
            // row insists the document exists and the disk says otherwise. Nothing
            // else records that divergence: the user sees a puzzling download failure
            // and, until now, the server said nothing at all.
            log.error("document.file_missing documentId={} owner={} expectedPath={} filename={}",
                    id, ownerId, resolved, document.getFilename());
            throw new DocumentNotFoundException("The stored file for this document is missing: " + id);
        }

        String contentType = document.getContentType() != null
                ? document.getContentType()
                : "application/octet-stream";

        return new DownloadableDocument(new PathResource(resolved), document.getFilename(), contentType);
    }

    /**
     * What would be destroyed along with this document. Month 3, Day 19.
     *
     * <p>Read-only, and the UI calls it BEFORE offering a confirmation so the question put to
     * the user is "delete this document and these two conversations?" rather than a bare
     * "are you sure?" followed by a failure.
     */
    @Transactional(readOnly = true)
    public DocumentDeletionImpact deletionImpact(UUID id, UUID ownerId) {
        Document document = documentRepository.findByIdAndOwner_Id(id, ownerId)
                .orElseThrow(() -> new DocumentNotFoundException("Document not found: " + id));

        // The other documents are fetched separately and grouped by session: one conversation
        // can cite many, so folding them into the per-chat query would multiply its rows and
        // make the message counts wrong.
        Map<UUID, List<DocumentDeletionImpact.ReferencedDocument>> othersBySession =
                citationRepository.findOtherDocumentsInChatsCiting(id, ownerId).stream()
                        .collect(Collectors.groupingBy(
                                CitationRepository.OtherDocument::getSessionId,
                                Collectors.mapping(
                                        row -> new DocumentDeletionImpact.ReferencedDocument(
                                                row.getDocumentId(), row.getFilename()),
                                        Collectors.toList())));

        List<DocumentDeletionImpact.AffectedChat> chats =
                citationRepository.findChatsCiting(id, ownerId).stream()
                        .map(row -> new DocumentDeletionImpact.AffectedChat(
                                row.getSessionId(), row.getTitle(), row.getMessageCount(),
                                othersBySession.getOrDefault(row.getSessionId(), List.of())))
                        .toList();

        return new DocumentDeletionImpact(id, document.getFilename(), chats);
    }

    /**
     * Deletes a document the caller owns, along with its bytes.
     *
     * <p><strong>{@code deleteLinkedChats} defaults to false and must stay that way.</strong>
     * {@code citations.document_id} is {@code ON DELETE RESTRICT}, so a document cited by a
     * conversation cannot be removed without removing that conversation — which is a decision
     * for the person who owns it, not a side effect of clicking a bin icon.
     *
     * <p>Without the flag this now raises {@link DocumentInUseException} (409) naming the
     * number of conversations, instead of letting the constraint surface as an opaque 500.
     * That alone fixes the symptom: the browser used to show "Failed to delete. The document
     * has been restored", which was true and told nobody anything.
     *
     * <p>With the flag, the conversations go first. Deleting a {@code chat_sessions} row
     * cascades in the database to its messages, their citations, its action audit rows and any
     * task created from it — so the ordering here is load-bearing: sessions, then the document,
     * then the bytes.
     */
    @Transactional
    public void deleteDocument(UUID id, UUID ownerId, boolean deleteLinkedChats) {
        Document document = documentRepository.findByIdAndOwner_Id(id, ownerId)
                .orElseThrow(() -> new DocumentNotFoundException("Document not found: " + id));

        List<UUID> citingSessions = citationRepository.findChatsCiting(id, ownerId).stream()
                .map(CitationRepository.AffectedChat::getSessionId)
                .toList();

        if (!citingSessions.isEmpty()) {
            if (!deleteLinkedChats) {
                throw new DocumentInUseException(citingSessions.size());
            }
            // Logged because it is destructive and irreversible, and because the count is the
            // thing somebody will want to check afterwards.
            log.warn("document.delete_cascade documentId={} owner={} conversationsDeleted={}",
                    id, ownerId, citingSessions.size());
            chatSessionRepository.deleteAllByIdInBatch(citingSessions);

            // THE ORDERING IS NOT ENOUGH ON ITS OWN. `deleteAllByIdInBatch` issues the DELETE
            // straight to the database, where it cascades to messages and their citations —
            // but Hibernate's persistence context still holds any Citation it has loaded, and
            // those still point at the Document about to be removed. The flush at commit then
            // fails with TransientPropertyValueException: a managed Citation referencing a
            // deleted Document. Clearing the context discards entities whose rows are already
            // gone, and the document is re-read below so what is deleted is a live instance.
            entityManager.flush();
            entityManager.clear();
            document = documentRepository.findByIdAndOwner_Id(id, ownerId)
                    .orElseThrow(() -> new DocumentNotFoundException("Document not found: " + id));
        }

        String storagePath = document.getStoragePath();
        documentRepository.delete(document);

        // Best-effort file cleanup AFTER the row is gone. A leftover file is clutter;
        // a row pointing at a deleted file would be a broken download, so the row is
        // the thing that must go first.
        if (storagePath != null) {
            try {
                Path root = Paths.get(uploadDir).toAbsolutePath().normalize();
                Path resolved = root.resolve(Paths.get(storagePath).getFileName()).normalize();
                if (resolved.startsWith(root)) {
                    Files.deleteIfExists(resolved);
                }
            } catch (IOException e) {
                log.warn("Deleted document {} but could not remove its file: {}", id, e.getMessage());
            }
        }
    }

    /** What the controller needs to stream a file back. */
    public record DownloadableDocument(PathResource resource, String filename, String contentType) {}
}
