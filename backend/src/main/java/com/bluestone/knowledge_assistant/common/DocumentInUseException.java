package com.bluestone.knowledge_assistant.common;

import org.springframework.http.HttpStatus;

/**
 * Deleting this document would destroy conversations that cite it.
 *
 * <p><strong>409, not 500, and that distinction is the whole reason this class exists.</strong>
 * {@code citations.document_id} is {@code ON DELETE RESTRICT}, so the delete used to fail as a
 * raw constraint violation — which surfaced to the browser as a generic failure and showed the
 * user <em>"Failed to delete. The document has been restored."</em> True, and useless: it names
 * no cause and offers no way forward, so the document simply looked undeletable.
 *
 * <p>The condition is not an error in the system. It is the system protecting a conversation
 * the user may still want, and the honest response is to say which conversations and let them
 * choose. {@code GET /api/documents/{id}/deletion-impact} answers that, and
 * {@code DELETE ?deleteLinkedChats=true} is the answer when they say yes.
 */
public class DocumentInUseException extends DomainException {
    public DocumentInUseException(int chatCount) {
        super(chatCount == 1
                        ? "This document is cited by 1 conversation. Deleting it would delete "
                          + "that conversation too."
                        : "This document is cited by " + chatCount + " conversations. Deleting it "
                          + "would delete those conversations too.",
                ErrorCode.DOCUMENT_IN_USE, HttpStatus.CONFLICT);
    }
}
