package com.knowledgeassistant.document;

import com.knowledgeassistant.common.PageRequestFactory;
import com.knowledgeassistant.common.dto.PageResponse;
import com.knowledgeassistant.document.dto.DocumentDeletionImpact;
import com.knowledgeassistant.document.dto.DocumentDto;
import com.knowledgeassistant.security.annotation.CurrentUserId;
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import com.knowledgeassistant.common.RateLimitProperties;
import com.knowledgeassistant.common.RateLimiter;
import org.springframework.web.multipart.MultipartFile;

import java.time.Duration;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    /**
     * Uploads per user per minute. Day 17.
     *
     * <p><strong>The cost of an upload changed on Day 16 and the limit follows it.</strong>
     * Until then an upload stored bytes: cheap, IO-bound, and nothing a limit was protecting.
     * It now runs extraction, chunking and embedding synchronously on the CPU — measured at
     * ~50ms per chunk, 1.5s for a 24-chunk PDF, and proportionally more for a large one — on
     * the same machine and the same cores serving every question.
     *
     * <p>So the resource being protected is not disk, it is the embedding model. Twenty a
     * minute is far beyond any human workflow and still bounds how much of the CPU one
     * account can take.
     */
    private final RateLimiter rateLimiter;
    private final RateLimitProperties rateLimits;

    

    private final DocumentService documentService;

    public DocumentController(DocumentService documentService, RateLimiter rateLimiter,
                              RateLimitProperties rateLimits) {
        this.rateLimiter = rateLimiter;
        this.rateLimits = rateLimits;
        this.documentService = documentService;
    }

    @Operation(summary = "List the caller's documents (paged)")
    @GetMapping
    public PageResponse<DocumentDto> getDocuments(@RequestParam(required = false) DocumentStatus status,
                                                  @RequestParam(required = false) String search,
                                                  @RequestParam(required = false) Integer page,
                                                  @RequestParam(required = false) Integer size,
                                                  @CurrentUserId UUID userId) {
        return documentService.getDocuments(userId, status, search, PageRequestFactory.of(page, size));
    }

    @Operation(summary = "Upload a new document")
    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<DocumentDto> upload(@RequestParam(value = "file", required = false) MultipartFile file,
                                              @CurrentUserId UUID userId) {
        // KEYED BY USER, not by IP. Upload requires authentication, so the user id is both
        // available and the thing actually worth limiting — one account should not be able
        // to monopolise the embedding model regardless of how many addresses it comes from.
        rateLimiter.check("upload", userId.toString(), rateLimits.uploadPerMinute(), Duration.ofMinutes(1));
        DocumentDto uploadedDoc = documentService.uploadDocument(file, userId);
        return ResponseEntity.status(HttpStatus.CREATED).body(uploadedDoc);
    }

    @Operation(summary = "Get document metadata by ID")
    @GetMapping("/{documentId}")
    public ResponseEntity<DocumentDto> getDocument(@PathVariable UUID documentId,
                                                   @CurrentUserId UUID userId) {
        return ResponseEntity.ok(documentService.getDocumentById(documentId, userId));
    }

    @Operation(summary = "Download the original file")
    @GetMapping("/{documentId}/download")
    public ResponseEntity<Resource> download(@PathVariable UUID documentId,
                                             @CurrentUserId UUID userId) {

        DocumentService.DownloadableDocument file = documentService.download(documentId, userId);

        // 'inline' so the browser renders a PDF or text in a tab rather than forcing a
        // save dialog — the user asked to OPEN the original, not to download it.
        // filename* is the RFC 5987 form, which survives non-ASCII names; the plain
        // filename stays as an ASCII-safe fallback for older clients.
        String encoded = URLEncoder.encode(file.filename(), StandardCharsets.UTF_8).replace("+", "%20");
        String disposition = "inline; filename=\"" + file.filename().replaceAll("[\"\\r\\n]", "") + "\""
                + "; filename*=UTF-8''" + encoded;

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .header(HttpHeaders.CONTENT_TYPE, file.contentType())
                // The bytes are per-user; a shared cache must never reuse this response.
                .header(HttpHeaders.CACHE_CONTROL, "private, no-store")
                .body(file.resource());
    }

    @Operation(summary = "What deleting this document would also delete",
            description = "Conversations that cite the document, which would be deleted with it. "
                    + "An empty list means the document can be deleted outright. Call this "
                    + "before offering a delete confirmation.")
    @GetMapping("/{documentId}/deletion-impact")
    public DocumentDeletionImpact deletionImpact(@PathVariable UUID documentId,
                                                 @CurrentUserId UUID userId) {
        return documentService.deletionImpact(documentId, userId);
    }

    @Operation(summary = "Delete a document and its stored file",
            description = "Returns 409 DOCUMENT_IN_USE if conversations cite this document. "
                    + "Pass deleteLinkedChats=true to delete them along with it — that is "
                    + "irreversible, so the caller must have confirmed it with the user first.")
    @DeleteMapping("/{documentId}")
    public ResponseEntity<Void> delete(@PathVariable UUID documentId,
                                       @RequestParam(defaultValue = "false") boolean deleteLinkedChats,
                                       @CurrentUserId UUID userId) {
        // Defaults to false deliberately: an existing client that has not been updated keeps
        // the safe behaviour and now gets a 409 explaining itself, rather than silently
        // destroying conversations because a query parameter was omitted.
        documentService.deleteDocument(documentId, userId, deleteLinkedChats);
        return ResponseEntity.noContent().build();
    }
}
