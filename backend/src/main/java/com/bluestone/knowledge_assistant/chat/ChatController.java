package com.bluestone.knowledge_assistant.chat;

import com.bluestone.knowledge_assistant.chat.dto.ChatSessionDto;
import com.bluestone.knowledge_assistant.common.PageRequestFactory;
import com.bluestone.knowledge_assistant.common.dto.PageResponse;
import com.bluestone.knowledge_assistant.chat.dto.CreateSessionRequest;
import com.bluestone.knowledge_assistant.chat.dto.MessageDto;
import com.bluestone.knowledge_assistant.chat.dto.MessageRequest;
import com.bluestone.knowledge_assistant.security.annotation.CurrentUserId;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/chat")
public class ChatController {

    private final ChatSessionService chatSessionService;

    public ChatController(ChatSessionService chatSessionService) {
        this.chatSessionService = chatSessionService;
    }

    @PostMapping("/sessions")
    public ResponseEntity<ChatSessionDto> createSession(@Valid @RequestBody CreateSessionRequest request,
                                                       @CurrentUserId UUID userId) {
        ChatSessionDto session = chatSessionService.createSession(userId, request.initialMessage(), request.model());
        return ResponseEntity.status(HttpStatus.CREATED).body(session);
    }

    @Operation(summary = "Get all chat sessions")
    @GetMapping("/sessions")
    public ResponseEntity<PageResponse<ChatSessionDto>> getSessions(
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size,
            @CurrentUserId UUID userId) {
        return ResponseEntity.ok(chatSessionService.getUserSessions(userId, PageRequestFactory.of(page, size)));
    }

    @Operation(summary = "Get messages for a specific session")
    @GetMapping("/{sessionId}/messages") // FIX: Restored to match contract
    public ResponseEntity<List<MessageDto>> getMessages(@PathVariable UUID sessionId,
                                                       @CurrentUserId UUID userId) {
        List<MessageDto> messages = chatSessionService.getSessionMessages(sessionId, userId);
        return ResponseEntity.ok(messages);
    }

    @Operation(summary = "Send a new message to an existing chat session")
    @io.swagger.v3.oas.annotations.parameters.RequestBody(
            content = @Content(
                    mediaType = "application/json",
                    examples = @ExampleObject(
                            name = "Standard Prompt",
                            value = "{\n  \"sessionId\": \"33333333-3333-3333-3333-333333333333\",\n  \"content\": \"What is the status of the runway?\"\n}"
                    )
            )
    )
    @PostMapping("/message") // FIX: Restored to match contract
    public ResponseEntity<MessageDto> addMessage(@Valid @RequestBody MessageRequest request,
                                                @CurrentUserId UUID userId) {
        // sessionId still comes from the body, but it is now validated against the caller
        MessageDto message = chatSessionService.sendMessage(request, userId);
        // FIX: Return 201 Created instead of 200 OK
        return ResponseEntity.status(HttpStatus.CREATED).body(message);
    }

    @Operation(summary = "Delete a chat session and its messages")
    @DeleteMapping("/sessions/{sessionId}")
    public ResponseEntity<Void> deleteSession(@PathVariable UUID sessionId,
                                              @CurrentUserId UUID userId) {
        chatSessionService.deleteSession(sessionId, userId);
        return ResponseEntity.noContent().build();
    }
}