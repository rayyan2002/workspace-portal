package com.bluestone.knowledge_assistant.chat;

import com.bluestone.knowledge_assistant.chat.dto.MessageRequest;
import com.bluestone.knowledge_assistant.common.ChatNotFoundException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.support.TransactionCallback;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ChatSessionServiceTest {

    @Mock
    private ChatSessionRepository chatSessionRepository;

    @Mock
    private MessageRepository messageRepository;

    @Mock
    private com.bluestone.knowledge_assistant.citation.CitationRepository citationRepository;

    @Mock
    private com.bluestone.knowledge_assistant.document.DocumentRepository documentRepository;

    @Mock
    private com.bluestone.knowledge_assistant.document.DocumentChunkRepository documentChunkRepository;

    @Mock
    private com.bluestone.knowledge_assistant.genai.GenAiClient genAiClient;

    @Mock
    private com.bluestone.knowledge_assistant.genai.GenAiProperties genAiProperties;

    /**
     * The transaction boundary is now a collaborator, not an annotation.
     *
     * <p>Day 8 moved the 30-58 second AI call OUT of the transaction: holding a pooled
     * connection for the length of a language-model call exhausts a ten-connection HikariCP
     * pool at the eleventh concurrent chat. The turn is split into persist-user /
     * call-AI / persist-reply, and {@link TransactionTemplate} is what makes those two
     * database phases transactional without wrapping the slow middle.
     *
     * <p>Mocking it means this unit test drives the real three-phase structure.
     */
    @Mock
    private TransactionTemplate transactionTemplate;

    /**
     * Day 14b: proposals are TRANSLATED here, not decided. Which tool a message asks for is
     * decided by the GenAI service, which is the only side holding a sentence encoder; this
     * collaborator turns its answer into the contracted shape and verifies the caller may
     * see the document named.
     */
    @Mock
    private ActionProposer actionProposer;

    @InjectMocks
    private ChatSessionService chatSessionService;

    private static final UUID USER_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");

    @Test
    void sendMessage_SavesUserAndAiMessages_AndUpdateSession() {
        // ARRANGE
        UUID sessionId = UUID.randomUUID();
        MessageRequest request = new MessageRequest(sessionId, "Hello AI", null);
        ChatSession mockSession = new ChatSession();

        // Run the transactional phases inline. The point of the split is WHERE the AI call
        // sits relative to them, and that structure is exercised either way.
        when(transactionTemplate.execute(any())).thenAnswer(
                i -> i.getArgument(0, TransactionCallback.class).doInTransaction(null));

        // Stub the session lookup to succeed
        // The lookup is now scoped: session id AND owner, in one query
        when(chatSessionRepository.findByIdAndUser_Id(sessionId, USER_ID)).thenReturn(Optional.of(mockSession));
        when(chatSessionRepository.findById(any())).thenReturn(Optional.of(mockSession));
        when(genAiClient.answer(any(), any(), any(), any(), any())).thenReturn(
                new com.bluestone.knowledge_assistant.genai.dto.GenAiAnswerResponse(
                        "grounded", "An answer.", java.util.List.of(), java.util.List.of(), null));

        // The service uses the value save() returns, as JPA code should; the default
        // mock answer of null would make that look like a bug in the service.
        when(messageRepository.save(any(Message.class))).thenAnswer(i -> i.getArgument(0));

        // ACT
        chatSessionService.sendMessage(request, USER_ID);

        // ASSERT & VERIFY
        // Prove the atomic interaction: Exactly 2 messages were saved
        verify(messageRepository, times(2)).save(any(Message.class));

        // With no ready documents to draw on, no citation is invented.
        verify(citationRepository, never()).save(any());

        // Prove the session was updated and saved
        verify(chatSessionRepository, times(1)).save(mockSession);
    }

    @Test
    void getSessionMessages_ThrowsException_WhenSessionNotFound() {
        // ARRANGE
        UUID sessionId = UUID.randomUUID();

        // Stub the scoped existence check to fail — this covers BOTH "no such session"
        // and "someone else's session", which is exactly the point of folding ownership
        // into the query rather than checking it afterwards.
        when(chatSessionRepository.existsByIdAndUser_Id(sessionId, USER_ID)).thenReturn(false);

        // ACT & ASSERT
        assertThrows(
                ChatNotFoundException.class,
                () -> chatSessionService.getSessionMessages(sessionId, USER_ID)
        );

        // Verify the message repository was NEVER queried
        verify(messageRepository, never()).findBySessionIdOrderByCreatedAtAsc(any());
    }
}