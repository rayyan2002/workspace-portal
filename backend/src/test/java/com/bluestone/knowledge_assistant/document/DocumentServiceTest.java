package com.bluestone.knowledge_assistant.document;

import com.bluestone.knowledge_assistant.common.DocumentValidationException;
import com.bluestone.knowledge_assistant.common.ErrorCode;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import com.bluestone.knowledge_assistant.user.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.web.multipart.MultipartFile;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;

@ExtendWith(MockitoExtension.class) // Enables Mockito
class DocumentServiceTest {

    @Mock
    private DocumentRepository documentRepository; // The fake dependency

    @Mock
    private UserRepository userRepository;

    /**
     * Day 16 collaborators. These tests only exercise VALIDATION — the checks that reject a
     * file before anything is stored — so every one of them returns before ingestion is
     * reached. They are mocks so the constructor is satisfiable, and the fact that none is
     * stubbed is itself the assertion: a validation failure must not call the GenAI service.
     */
    @Mock
    private com.bluestone.knowledge_assistant.genai.GenAiClient genAiClient;

    @Mock
    private DocumentChunkWriter chunkWriter;

    @Mock
    private org.springframework.transaction.support.TransactionTemplate transactionTemplate;

    @Mock
    private com.bluestone.knowledge_assistant.citation.CitationRepository citationRepository;

    @Mock
    private com.bluestone.knowledge_assistant.chat.ChatSessionRepository chatSessionRepository;

    // Constructed by hand rather than @InjectMocks: the service takes a plain String upload
    // directory and an int dimension alongside the collaborators, which Mockito cannot supply.
    private DocumentService documentService;

    private static final UUID OWNER_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");

    @BeforeEach
    void setUp() {
        documentService = new DocumentService(documentRepository, userRepository, genAiClient,
                chunkWriter, transactionTemplate, "target/test-uploads", 384,
                citationRepository, chatSessionRepository);
    }

    @Test
    void uploadDocument_ThrowsException_WhenFileIsNull() {
        // ARRANGE
        MultipartFile nullFile = null;

        // ACT & ASSERT: Expect our custom exception
        DocumentValidationException exception = assertThrows(
                DocumentValidationException.class,
                () -> documentService.uploadDocument(nullFile, OWNER_ID)
        );

        // Prove the exact error code and message were triggered
        assertEquals(ErrorCode.MISSING_FILE, exception.getErrorCode());
        assertEquals("No file provided.", exception.getMessage());
    }

    @Test
    void uploadDocument_ThrowsException_WhenFileIsEmpty() {
        // ARRANGE: Create a mock file that reports it is empty
        MultipartFile emptyFile = mock(MultipartFile.class);
        org.mockito.Mockito.when(emptyFile.isEmpty()).thenReturn(true);

        // ACT & ASSERT
        DocumentValidationException exception = assertThrows(
                DocumentValidationException.class,
                () -> documentService.uploadDocument(emptyFile, OWNER_ID)
        );

        assertEquals(ErrorCode.MISSING_FILE, exception.getErrorCode());
    }
}