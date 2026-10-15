package com.knowledgeassistant.document;

import com.knowledgeassistant.user.User;
import jakarta.persistence.*;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "documents")
public class Document {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", updatable = false, nullable = false)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "owner_id", nullable = false)
    private User owner;

    @Column(name = "filename", nullable = false)
    private String filename;

    @Column(name = "size_bytes", nullable = false)
    private Long sizeBytes;

    @Column(name = "upload_date", nullable = false)
    private Instant uploadDate;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private DocumentStatus status;

    /**
     * Where the bytes live, relative to the configured upload root — never absolute,
     * which would not survive a redeploy or a different machine.
     */
    @Column(name = "storage_path", length = 512)
    private String storagePath;

    /** Recorded at upload so the download can be served with an honest Content-Type. */
    @Column(name = "content_type")
    private String contentType;

    // Protected no-args constructor required by JPA
    protected Document() {}

    public Document(User owner, String filename, Long sizeBytes, Instant uploadDate,
                    DocumentStatus status, String contentType) {
        this.owner = owner;
        this.filename = filename;
        this.sizeBytes = sizeBytes;
        this.uploadDate = uploadDate;
        this.status = status;
        this.contentType = contentType;
    }

    // Getters
    public UUID getId() { return id; }
    public User getOwner() { return owner; }
    public String getFilename() { return filename; }
    public Long getSizeBytes() { return sizeBytes; }
    public Instant getUploadDate() { return uploadDate; }
    public DocumentStatus getStatus() { return status; }
    public String getStoragePath() { return storagePath; }
    public String getContentType() { return contentType; }

    // Setters (Only for mutable fields)
    public void setStatus(DocumentStatus status) { this.status = status; }
    public void setStoragePath(String storagePath) { this.storagePath = storagePath; }
}
