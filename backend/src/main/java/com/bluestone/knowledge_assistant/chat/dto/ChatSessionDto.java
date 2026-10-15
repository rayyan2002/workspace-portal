package com.bluestone.knowledge_assistant.chat.dto;

import com.bluestone.knowledge_assistant.chat.ChatSession;

import java.time.Instant;
import java.util.UUID;

public record ChatSessionDto(
        UUID id,
        String title,
        Instant createdAt,
        Instant updatedAt,
        String lastMessagePreview,

        /**
         * The assistant's reply to the message that opened this conversation, present
         * only on the create response. Additive: list endpoints leave it null.
         *
         * <p>It has to travel with the create response because action proposals are
         * never persisted — refetching history would return the message without them,
         * which is exactly why the first message of a chat could not propose a task.
         */
        MessageDto initialResponse
) {
    // Static factory mapping Entity -> DTO.
    // Notice we do NOT map session.getUser() here, safely avoiding the LazyInitializationException trap.
    public static ChatSessionDto from(ChatSession session) {
        return from(session, null);
    }

    public static ChatSessionDto from(ChatSession session, MessageDto initialResponse) {
        return new ChatSessionDto(
                session.getId(),
                session.getTitle(),
                session.getCreatedAt(),
                session.getUpdatedAt(),
                session.getLastMessagePreview(),
                initialResponse
        );
    }
}
