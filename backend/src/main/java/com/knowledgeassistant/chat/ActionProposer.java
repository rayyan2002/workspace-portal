package com.knowledgeassistant.chat;

import com.knowledgeassistant.action.ActionType;
import com.knowledgeassistant.chat.dto.ActionProposalDto;
import com.knowledgeassistant.document.Document;
import com.knowledgeassistant.document.DocumentRepository;
import com.knowledgeassistant.document.DocumentStatus;
import com.knowledgeassistant.genai.dto.GenAiProposal;
import com.knowledgeassistant.task.TaskPriority;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * Turns what the GenAI service proposed into what the frontend and the governance flow read.
 *
 * <p><strong>Day 14b. This class replaces a keyword trigger list that used to live in {@link
 * ChatSessionService}.</strong> Routing moved to the GenAI service because that is the only
 * side holding the sentence encoder, and therefore the only side that can run a classifier
 * instead of matching strings somebody thought of. What is LEFT here is translation, and
 * translation is genuinely Spring's job: it owns the {@code documents} table, so it is the
 * only side that can turn a document id into a filename or verify that the caller may see it.
 *
 * <p><strong>THIS IS WHERE THE ORDINAL-TO-DOCUMENT BRIDGE FINALLY EXISTS.</strong>
 * {@code INTEGRATION_CONTRACT.md} §5 specified it from Day 10: the model quotes a sentence,
 * the service resolves the quote to a chunk, and SPRING maps that to the document row it
 * wrote. {@link com.knowledgeassistant.action.dto.SummarizePayload} needs
 * {@code {documentId, documentName}} and the published tool schema carries a
 * {@code chunk_ordinal} — and for five days NOTHING PERFORMED THE TRANSLATION. Jackson
 * failed closed on the mismatch rather than nulling it, so it was latent rather than silent;
 * it was also unreachable, because nothing proposed the tool. Both of those are now false.
 *
 * <p><strong>EVERY PROPOSAL IS REBUILT, NEVER FORWARDED.</strong> The service's
 * {@code arguments} map does not reach the browser: each field is read, validated against
 * the same bounds the database enforces, and written into a fresh payload. A proposal that
 * fails any check is DROPPED AND LOGGED, and the answer is unaffected — a suggestion is not
 * worth losing a reply over, and a malformed suggestion is worth losing entirely.
 *
 * <p>Nothing here writes. A proposal is a suggestion addressed to a human; {@link
 * com.knowledgeassistant.action.ActionService} records a row for every decision
 * including rejections, and only an approval has an effect.
 */
@Component
public class ActionProposer {

    private static final Logger log = LoggerFactory.getLogger(ActionProposer.class);

    /** Matches {@code tasks.title VARCHAR(255)} and the published CreateTaskArguments bound. */
    private static final int TITLE_MAX = 255;
    private static final int QUERY_MAX = 500;
    private static final int LABEL_MAX = 120;

    private final DocumentRepository documentRepository;

    public ActionProposer(DocumentRepository documentRepository) {
        this.documentRepository = documentRepository;
    }

    /**
     * Translates the service's proposals, dropping any that cannot be made safe.
     *
     * <p>Read-only, and short: it runs inside the turn's final transaction and does at most
     * one document lookup.
     *
     * @return null when nothing survives, because {@code MessageDto.actions} is absent
     *         rather than empty in the published contract and the frontend's
     *         {@code ActionProposal[]} is optional.
     */
    @Transactional(readOnly = true)
    public List<ActionProposalDto> translate(List<GenAiProposal> proposals, UUID userId) {
        if (proposals == null || proposals.isEmpty()) {
            return null;
        }

        List<ActionProposalDto> translated = new ArrayList<>();
        for (GenAiProposal proposal : proposals) {
            try {
                toDto(proposal, userId).ifPresent(translated::add);
            } catch (RuntimeException failure) {
                // A proposal must never cost the user their answer. This catch is the
                // reason GenAiProposal.arguments is an untyped map rather than a Jackson
                // polymorphic union — a union would have thrown during deserialisation of
                // the whole response, where there is nothing left to salvage.
                log.warn("proposal.untranslatable label={} — dropped",
                        proposal == null ? null : proposal.label(), failure);
            }
        }
        return translated.isEmpty() ? null : translated;
    }

    private Optional<ActionProposalDto> toDto(GenAiProposal proposal, UUID userId) {
        if (proposal == null || proposal.arguments() == null) {
            return Optional.empty();
        }
        Map<String, Object> args = proposal.arguments();
        String tool = string(args.get("tool"));
        if (tool == null) {
            log.warn("proposal.no_tool args={}", args.keySet());
            return Optional.empty();
        }

        // ActionType.fromValue throws on an unknown name, which is the behaviour wanted:
        // "delete-everything" is not a typo for "create-task" and nothing here guesses what
        // the service meant. The throw is caught by translate() and the proposal is dropped.
        ActionType type = ActionType.fromValue(tool);

        return switch (type) {
            case CREATE_TASK -> createTask(args, proposal.label());
            case SUMMARIZE_DOCUMENT -> summarizeDocument(args, proposal.label(), userId);
            case LOOKUP_KNOWLEDGE -> lookupKnowledge(args, proposal.label());
        };
    }

    private Optional<ActionProposalDto> createTask(Map<String, Object> args, String label) {
        String title = string(args.get("title"));
        if (title == null || title.length() > TITLE_MAX) {
            // Over-long is dropped rather than truncated: a task whose title was silently
            // cut is a different task from the one the user was shown and approved.
            log.warn("proposal.create_task.bad_title length={}", title == null ? -1 : title.length());
            return Optional.empty();
        }
        TaskPriority priority = priority(args.get("priority"));
        if (priority == null) {
            return Optional.empty();
        }
        return Optional.of(dto(ActionType.CREATE_TASK, label, "Create a task: " + title,
                Map.of("title", title, "priority", priority.name())));
    }

    /**
     * The translation the contract has specified since Day 10 and nothing implemented.
     *
     * <p>The service resolves its own {@code chunk_ordinal} to a {@code document_id} in code
     * — the model never states an identifier, because a UUID costs 36 tokens and measurably
     * stops a 0.5B model citing at all. Spring supplies the second half: the filename, and
     * the only ownership check that means anything.
     *
     * <p><strong>Ownership is re-verified here, not trusted.</strong> The id crossed a
     * network boundary, so it is a claim. The rule applied is the same one that builds
     * {@code allowed_document_ids} in the first place — owned AND ready — so a proposal can
     * only ever name a document the user could already have asked about. Without this check
     * the service could name any document in the table and Spring would put its filename on
     * screen.
     */
    private Optional<ActionProposalDto> summarizeDocument(Map<String, Object> args, String label,
                                                          UUID userId) {
        UUID documentId = uuid(args.get("document_id"));
        if (documentId == null) {
            // The service resolves this in code and drops the proposal when it cannot. A
            // null arriving here means an ordinal that resolved to nothing, so there is no
            // document to summarise and no honest payload to build.
            log.warn("proposal.summarize.unresolved chunk_ordinal={}", args.get("chunk_ordinal"));
            return Optional.empty();
        }
        Optional<Document> document = documentRepository.findById(documentId)
                .filter(d -> d.getOwner() != null && userId.equals(d.getOwner().getId()))
                .filter(d -> d.getStatus() == DocumentStatus.ready);
        if (document.isEmpty()) {
            log.warn("proposal.summarize.not_available documentId={} userId={}", documentId, userId);
            return Optional.empty();
        }

        String filename = document.get().getFilename();
        return Optional.of(dto(ActionType.SUMMARIZE_DOCUMENT, label,
                "Summarise " + filename,
                // Both fields SummarizePayload needs, which is the whole point of this method.
                Map.of("documentId", documentId.toString(), "documentName", filename)));
    }

    private Optional<ActionProposalDto> lookupKnowledge(Map<String, Object> args, String label) {
        String query = string(args.get("query"));
        if (query == null || query.length() > QUERY_MAX) {
            log.warn("proposal.lookup.bad_query length={}", query == null ? -1 : query.length());
            return Optional.empty();
        }
        return Optional.of(dto(ActionType.LOOKUP_KNOWLEDGE, label,
                "Search your documents for: " + query, Map.of("query", query)));
    }

    /**
     * @param fallbackLabel used when the service sent no usable label. The service writes a
     *                      better one than a constant — that was the Day 10 complaint about
     *                      "Create a tracking task for this request" — but the UI must have
     *                      SOMETHING on the approve button, and an empty control is a bug a
     *                      user cannot work around.
     */
    private ActionProposalDto dto(ActionType type, String label, String fallbackLabel,
                                  Map<String, Object> payload) {
        String shown = (label == null || label.isBlank()) ? fallbackLabel : label;
        return ActionProposalDto.fresh(
                // Spring mints the id, because Spring owns the row it becomes:
                // action_audit.action_id. The service deliberately sends none.
                "act-" + UUID.randomUUID(),
                type.getValue(),
                shown.length() > LABEL_MAX ? shown.substring(0, LABEL_MAX) : shown,
                payload);
    }

    private static String string(Object value) {
        if (!(value instanceof String s) || s.isBlank()) {
            return null;
        }
        return s.strip();
    }

    private static TaskPriority priority(Object value) {
        String raw = string(value);
        if (raw == null) {
            return null;
        }
        try {
            return TaskPriority.valueOf(raw);
        } catch (IllegalArgumentException unknown) {
            log.warn("proposal.create_task.bad_priority value={}", raw);
            return null;
        }
    }

    private static UUID uuid(Object value) {
        String raw = string(value);
        if (raw == null) {
            return null;
        }
        try {
            return UUID.fromString(raw);
        } catch (IllegalArgumentException malformed) {
            log.warn("proposal.bad_uuid value={}", raw);
            return null;
        }
    }
}
