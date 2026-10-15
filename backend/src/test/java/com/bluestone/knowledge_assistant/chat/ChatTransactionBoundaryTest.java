package com.bluestone.knowledge_assistant.chat;

import com.bluestone.knowledge_assistant.chat.dto.MessageRequest;
import com.bluestone.knowledge_assistant.genai.GenAiClient;
import com.bluestone.knowledge_assistant.genai.dto.GenAiAnswerResponse;
import com.bluestone.knowledge_assistant.support.TestFixtures;
import com.bluestone.knowledge_assistant.user.User;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentMatchers;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.assertFalse;

/**
 * The one claim Day 8 makes that every other test was structurally unable to check.
 *
 * <p><strong>Deliberately NOT {@code @Transactional}.</strong> Every other chat test is, and
 * that is exactly why they could not catch this: a test-managed transaction wraps the service
 * call, so the service joins it and "is a transaction active?" is always true regardless of
 * what the service does. The suite went green on a boundary that did not exist.
 *
 * <p>What it caught: removing {@code @Transactional} from {@code sendMessage} did not take it
 * out of a transaction. {@code ChatSessionService} is annotated
 * {@code @Transactional(readOnly = true)} at the CLASS level, which applies to every public
 * method — so the method still ran inside a transaction, the {@link
 * org.springframework.transaction.support.TransactionTemplate} phases joined it rather than
 * opening their own, and a pooled connection was held across the entire 30-60 second model
 * call. The fix is {@code Propagation.NOT_SUPPORTED} on the entry methods, which SUSPENDS the
 * class-level transaction instead of inheriting it.
 *
 * <p>Because nothing rolls back here, the fixture cleans up after itself.
 */
@SpringBootTest
@ActiveProfiles("test")
class ChatTransactionBoundaryTest {

    @MockitoBean private GenAiClient genAiClient;
    @Autowired private ChatSessionService chatSessionService;
    @Autowired private TestFixtures fixtures;

    private User owner;
    private final AtomicBoolean transactionActiveDuringAiCall = new AtomicBoolean(true);

    @BeforeEach
    void setUp() {
        owner = fixtures.user();

        // The probe: record whether a transaction is open at the exact moment the slow call
        // would be in flight. This is the assertion the whole three-phase split exists for.
        Mockito.when(genAiClient.answer(ArgumentMatchers.anyString(), ArgumentMatchers.anyList(),
                        ArgumentMatchers.any(), ArgumentMatchers.anyList(), ArgumentMatchers.any()))
                .thenAnswer(invocation -> {
                    transactionActiveDuringAiCall.set(
                            TransactionSynchronizationManager.isActualTransactionActive());
                    return new GenAiAnswerResponse("grounded", "An answer.", List.of(), List.of(), null);
                });
    }

    @AfterEach
    void tearDown() {
        fixtures.cleanUp();
    }

    @Test
    void createSession_holdsNoDatabaseConnection_whileTheModelIsGenerating() {
        chatSessionService.createSession(owner.getId(), "What does the report say?", null);

        assertFalse(transactionActiveDuringAiCall.get(),
                "A transaction was open during the AI call. HikariCP defaults to ten connections, "
                        + "so ten concurrent chats would hold the whole pool for 30-60s each while "
                        + "their threads waited on an HTTP socket.");
    }

    @Test
    void sendMessage_holdsNoDatabaseConnection_whileTheModelIsGenerating() {
        var session = fixtures.session(owner, "Airport Operations Review");

        chatSessionService.sendMessage(new MessageRequest(session.getId(), "anything", null), owner.getId());

        assertFalse(transactionActiveDuringAiCall.get(),
                "A transaction was open during the AI call.");
    }
}
