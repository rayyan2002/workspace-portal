package com.knowledgeassistant.document.dto;

import io.swagger.v3.oas.annotations.media.Schema;

import java.util.List;
import java.util.UUID;

/**
 * What would be destroyed along with a document. Month 3, Day 19.
 *
 * <p>Answers the question the UI has to ask before it can offer a safe confirmation:
 * <em>"if I delete this, what else goes?"</em> Previously nothing could answer it — the
 * delete simply failed on a foreign key and the user was told the document "has been
 * restored", which named no cause.
 *
 * <p>An empty {@code chats} list means the document can be deleted outright.
 */
@Schema(description = "What deleting a document would also delete")
public record DocumentDeletionImpact(
        @Schema(description = "The document that would be deleted")
        UUID documentId,

        String filename,

        @Schema(description = "Conversations that cite this document and would be deleted with it")
        List<AffectedChat> chats) {

    /**
     * One conversation that would go.
     *
     * <p>{@code otherDocuments} is the honest part. A chat is not necessarily <em>about</em>
     * the document being deleted: on the live corpus a ten-message conversation titled
     * "tell me about finance" cites four documents, and deleting any one of them takes the
     * whole conversation. A confirmation that showed only titles would conceal that.
     */
    @Schema(description = "A conversation that cites the document")
    public record AffectedChat(
            UUID id,
            String title,
            @Schema(description = "How many messages would be lost with it")
            long messageCount,
            @Schema(description = "The OTHER documents this conversation also draws on. "
                    + "These documents are NOT deleted — only the conversation is.")
            List<ReferencedDocument> otherDocuments) {}

    /** Another document an affected conversation refers to. It survives the deletion. */
    @Schema(description = "A document the conversation also cites, which is NOT deleted")
    public record ReferencedDocument(UUID id, String filename) {}

    public boolean isBlocked() {
        return !chats.isEmpty();
    }
}
