package com.knowledgeassistant.action;

import com.knowledgeassistant.action.dto.ActionRequest;
import com.knowledgeassistant.action.dto.ActionResult;
import com.knowledgeassistant.action.dto.CreateTaskPayload;
import com.knowledgeassistant.chat.ChatSessionRepository;
import com.knowledgeassistant.common.ChatNotFoundException;
import com.knowledgeassistant.task.TaskPriority;
import com.knowledgeassistant.task.TaskRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ActionServiceTest {

    @Mock
    private ActionAuditRepository actionAuditRepository;

    @Mock
    private TaskRepository taskRepository;

    // Added the missing mock to prevent the NullPointerException
    @Mock
    private ChatSessionRepository chatSessionRepository;

    @Mock
    private com.knowledgeassistant.document.DocumentRepository documentRepository;

    @Mock
    private com.knowledgeassistant.genai.GenAiClient genAiClient;

    /**
     * The transaction boundary is a collaborator now, not an annotation.
     *
     * <p>Summarising calls a language model for 15-60 seconds. A transaction spanning that
     * holds a pooled connection for its whole duration, and the pool is ten — so the audit
     * write, the AI call and the task write are three separate steps with the slow one
     * outside any transaction. Day 8 learned this the hard way on the chat path.
     */
    @Mock
    private org.springframework.transaction.support.TransactionTemplate transactionTemplate;

    @InjectMocks
    private ActionService actionService;

    private static final UUID USER_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");

    /**
     * Runs the transactional phases inline. What matters is WHERE the AI call sits relative
     * to them, and that structure is exercised either way.
     */
    private void runTransactionsInline() {
        org.mockito.Mockito.when(transactionTemplate.execute(org.mockito.ArgumentMatchers.any()))
                .thenAnswer(i -> i.getArgument(0,
                        org.springframework.transaction.support.TransactionCallback.class)
                        .doInTransaction(null));
    }

    @Test
    void processAction_WhenRejected_SavesAuditOnly() {
        runTransactionsInline();
        // ARRANGE
        CreateTaskPayload payload = new CreateTaskPayload("Test Task", TaskPriority.high);
        ActionRequest request = new ActionRequest(
                "act-123",
                UUID.randomUUID(),
                ActionDecision.rejected,
                ActionType.CREATE_TASK,
                payload
        );

        // Session exists AND belongs to this caller
        when(chatSessionRepository.existsByIdAndUser_Id(any(UUID.class), any(UUID.class))).thenReturn(true);

        // ACT
        ActionResult result = actionService.processAction(request, USER_ID);

        // ASSERT: rejected decision maps to a 'rejected' execution status
        assertEquals(ActionStatus.rejected, result.status());

        // Verify behavior: Audit was saved exactly once, task was NEVER saved
        verify(actionAuditRepository, times(1)).save(any(ActionAudit.class));
        verify(taskRepository, never()).save(any());
    }

    @Test
    void processAction_WhenApproved_SavesTaskAndAudit() {
        runTransactionsInline();
        // ARRANGE
        CreateTaskPayload payload = new CreateTaskPayload("Test Task", TaskPriority.high);
        ActionRequest request = new ActionRequest(
                "act-456",
                UUID.randomUUID(),
                ActionDecision.approved,
                ActionType.CREATE_TASK,
                payload
        );

        // Session exists AND belongs to this caller
        when(chatSessionRepository.existsByIdAndUser_Id(any(UUID.class), any(UUID.class))).thenReturn(true);

        // ACT
        ActionResult result = actionService.processAction(request, USER_ID);

        // ASSERT: approved decision maps to a 'completed' execution status
        assertEquals(ActionStatus.completed, result.status());

        // Verify behavior: Both repositories were called exactly once
        verify(actionAuditRepository, times(1)).save(any(ActionAudit.class));
        verify(taskRepository, times(1)).save(any());
    }

    @Test
    void processAction_ThrowsException_WhenSessionNotFound() {
        // ARRANGE
        CreateTaskPayload payload = new CreateTaskPayload("Test Task", TaskPriority.high);
        ActionRequest request = new ActionRequest(
                "act-789",
                UUID.randomUUID(),
                ActionDecision.approved,
                ActionType.CREATE_TASK,
                payload
        );

        // The edge case, now doing double duty: the session either does not exist or is
        // not the caller's. Both resolve to the same "not found", by design.
        when(chatSessionRepository.existsByIdAndUser_Id(any(UUID.class), any(UUID.class))).thenReturn(false);

        // ACT & ASSERT: Expect the exception to be thrown
        assertThrows(
                ChatNotFoundException.class,
                () -> actionService.processAction(request, USER_ID)
        );

        // Verify behavior: Because it threw an exception immediately, nothing should be saved
        verify(actionAuditRepository, never()).save(any());
        verify(taskRepository, never()).save(any());
    }
}