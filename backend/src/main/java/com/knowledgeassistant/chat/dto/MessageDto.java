package com.knowledgeassistant.chat.dto;

import com.knowledgeassistant.chat.Message;
import java.util.List;
import java.util.UUID;

public record MessageDto(
        UUID id,
        String content,
        String sender,
        String timestamp, // Adjust to Instant if your codebase uses Instant here
        List<CitationDto> citations,
        List<ActionProposalDto> actions,

        /**
         * Words corrected before retrieval, so the UI can say what was actually searched for.
         *
         * <p>EPHEMERAL, like action proposals and for the same reason: it describes THIS
         * turn's retrieval, not a fact about the message. Reloading the history shows the
         * answer without it, which is correct — the correction is something the user needed
         * to be told at the moment of answering, not a property of what was said.
         *
         * <p>Empty on every message that retrieved normally, which is almost all of them.
         */
        List<SpellingCorrectionDto> corrections
) {
    /** What the user typed, and the corpus word it was searched as. */
    public record SpellingCorrectionDto(String typed, String used) {}

    /** History: citations are persisted, so they load; action proposals are ephemeral. */
    public static MessageDto from(Message message, List<CitationDto> citations) {
        return new MessageDto(
                message.getId(),
                message.getContent(),
                message.getSender().name(),
                message.getCreatedAt() != null ? message.getCreatedAt().toString() : null,
                citations,
                null,
                // History: the correction was advice at the moment of answering, not a
                // property of the message. It is not persisted and must not be invented here.
                List.of());
    }

    /** Live response: carries both its sources and any action it is proposing. */
    public static MessageDto from(Message message, List<CitationDto> citations, List<ActionProposalDto> actions) {
        return new MessageDto(
                message.getId(),
                message.getContent(),
                message.getSender().name(),
                message.getCreatedAt() != null ? message.getCreatedAt().toString() : null,
                citations,
                actions,
                List.of());
    }

    /** Live response where retrieval corrected the question before searching. */
    public static MessageDto from(Message message, List<CitationDto> citations,
                                  List<ActionProposalDto> actions,
                                  List<SpellingCorrectionDto> corrections) {
        return new MessageDto(
                message.getId(),
                message.getContent(),
                message.getSender().name(),
                message.getCreatedAt() != null ? message.getCreatedAt().toString() : null,
                citations,
                actions,
                corrections == null ? List.of() : corrections);
    }

    public static MessageDto from(Message message) {
        return from(message, null);
    }
}
