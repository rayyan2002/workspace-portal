package com.knowledgeassistant.document.dto;

import com.knowledgeassistant.document.Document;
import com.knowledgeassistant.document.DocumentStatus;

import java.time.Instant;
import java.util.UUID;

public record DocumentDto(
        UUID id,
        String filename,
        Long sizeBytes,
        Instant uploadDate,
        DocumentStatus status
) {
    // Static factory for clean Entity -> DTO mapping
    public static DocumentDto from(Document document) {
        return new DocumentDto(
                document.getId(),
                document.getFilename(),
                document.getSizeBytes(),
                document.getUploadDate(),
                document.getStatus()
        );
    }
}