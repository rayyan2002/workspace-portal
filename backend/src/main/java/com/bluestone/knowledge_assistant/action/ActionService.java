package com.bluestone.knowledge_assistant.action;

import com.bluestone.knowledge_assistant.action.dto.ActionRequest;
import com.bluestone.knowledge_assistant.action.dto.ActionResult;
import com.bluestone.knowledge_assistant.action.dto.CreateTaskPayload;
import com.bluestone.knowledge_assistant.action.dto.LookupPayload;
import com.bluestone.knowledge_assistant.action.dto.LookupResult;
import com.bluestone.knowledge_assistant.action.dto.SummarizePayload;
import com.bluestone.knowledge_assistant.action.dto.SummarizeResult;
import com.bluestone.knowledge_assistant.action.dto.ActionAuditDto;
import com.bluestone.knowledge_assistant.chat.ChatSessionRepository;
import com.bluestone.knowledge_assistant.common.ChatNotFoundException;
import com.bluestone.knowledge_assistant.common.dto.PageResponse;
import com.bluestone.knowledge_assistant.document.Document;
import com.bluestone.knowledge_assistant.document.DocumentChunk;
import com.bluestone.knowledge_assistant.document.DocumentChunkRepository;
import com.bluestone.knowledge_assistant.document.DocumentRepository;
import com.bluestone.knowledge_assistant.document.DocumentStatus;
import com.bluestone.knowledge_assistant.genai.GenAiClient;
import com.bluestone.knowledge_assistant.genai.dto.GenAiAnswerResponse;
import com.bluestone.knowledge_assistant.genai.dto.GenAiCitation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import com.bluestone.knowledge_assistant.task.Task;
import com.bluestone.knowledge_assistant.task.TaskRepository;
import com.bluestone.knowledge_assistant.task.TaskStatus;
import com.bluestone.knowledge_assistant.task.dto.TaskDto;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class ActionService {

    private static final Logger log = LoggerFactory.getLogger(ActionService.class);

    /** What the GenAI service is asked when a summary is approved. */
    private static final String SUMMARISE_QUESTION =
            "Summarise this document. What is it about and what are its main points?";

    private final ChatSessionRepository chatSessionRepository;
    private final ActionAuditRepository actionAuditRepository;
    private final TaskRepository taskRepository;
    private final DocumentRepository documentRepository;
    private final DocumentChunkRepository documentChunkRepository;
    private final GenAiClient genAiClient;
    private final TransactionTemplate transactionTemplate;

    public ActionService(ChatSessionRepository chatSessionRepository,
                         ActionAuditRepository actionAuditRepository,
                         TaskRepository taskRepository,
                         DocumentRepository documentRepository,
                         DocumentChunkRepository documentChunkRepository,
                         GenAiClient genAiClient,
                         TransactionTemplate transactionTemplate) {
        this.chatSessionRepository = chatSessionRepository;
        this.actionAuditRepository = actionAuditRepository;
        this.taskRepository = taskRepository;
        this.documentRepository = documentRepository;
        this.documentChunkRepository = documentChunkRepository;
        this.genAiClient = genAiClient;
        this.transactionTemplate = transactionTemplate;
    }

    /**
     * Records a human's decision and, if approved, carries it out.
     *
     * <p><strong>Deliberately NOT {@code @Transactional}, and the class-level annotation was
     * removed for the same reason.</strong> Summarising calls a language model: 15-60
     * seconds measured. A transaction spanning that holds a pooled connection for its whole
     * duration, and HikariCP defaults to ten — the eleventh concurrent approval would block
     * on connection acquisition while ten threads sat waiting on an HTTP socket.
     *
     * <p>Day 8 found exactly this on the chat path, and found it the hard way: removing
     * {@code @Transactional} from the METHOD did nothing, because the annotation on the
     * CLASS still applied. Every test passed on a boundary that did not exist, because the
     * tests were themselves {@code @Transactional} and the service simply joined their
     * transaction. The fix there and here is to remove the blanket annotation and let each
     * method declare what it needs.
     *
     * <p>So: the audit write takes a short transaction of its own, the AI call happens
     * outside one, and the task write takes another.
     */
    public ActionResult processAction(ActionRequest request, UUID userId) {
        // 1. Session must exist AND belong to the caller. Existence alone was the hole:
        //    any known sessionId let anyone write an audit row — and an approved
        //    create-task — into someone else's session.
        if (!chatSessionRepository.existsByIdAndUser_Id(request.sessionId(), userId)) {
            throw new ChatNotFoundException("Chat session not found: " + request.sessionId());
        }

        // 2. IDEMPOTENCY. A proposal is decided once; deciding it again returns what the
        //    first decision produced rather than doing it a second time.
        //
        //    This is not defensive programming. Before V20 this table had five proposals
        //    decided twice — two approved+approved (two tasks from one click), and one
        //    rejected+approved where a human declined an action and it ran anyway. A
        //    double-click, a retried request or a back-button was enough.
        //
        //    Returning the original outcome rather than a 409: a double-click is not an
        //    error, and that is what "idempotent" means. The caller sees the same answer it
        //    would have seen the first time.
        var existing = actionAuditRepository.findByActionId(request.actionId());
        if (existing.isPresent()) {
            ActionAudit first = existing.get();
            log.info("action.repeat actionId={} firstDecision={} — not executed again",
                    request.actionId(), first.getDecision());
            return new ActionResult(
                    request.actionId(),
                    first.getDecision() == ActionDecision.approved
                            ? ActionStatus.completed
                            : ActionStatus.rejected,
                    request.type(),
                    // The original side effect is not replayed and its result was never
                    // stored, so there is nothing truthful to return here. Null is honest;
                    // re-running to regenerate it would defeat the point.
                    null, null);
        }

        // 3. ALWAYS write the audit log, regardless of decision — and BEFORE executing.
        //    That ordering was incidental until V20 and is now load-bearing: the UNIQUE
        //    constraint on action_id means a duplicate insert fails here, so the side effect
        //    below never happens.
        transactionTemplate.execute(status -> actionAuditRepository.save(new ActionAudit(
                request.actionId(),
                request.sessionId(),
                request.type(),
                request.decision(),
                Instant.now()
        )));

        // 3. EXECUTE side-effects ONLY if approved
        Object resultData = null;
        if (request.decision() == ActionDecision.approved) {

            if (request.type() == ActionType.CREATE_TASK && request.payload() instanceof CreateTaskPayload p) {
                // Real DB Execution
                Task task = new Task(
                        p.title(),
                        p.priority(),
                        TaskStatus.todo, // Default to todo per contract
                        Instant.now(),
                        request.sessionId()
                );
                transactionTemplate.execute(status -> taskRepository.save(task));
                resultData = TaskDto.from(task);

            } else if (request.type() == ActionType.SUMMARIZE_DOCUMENT
                    && request.payload() instanceof SummarizePayload p) {
                try {
                    resultData = summarise(p, userId);
                } catch (Exception failure) {
                    // FAILED is now producible. The value has existed in ActionStatus since
                    // Month 2 with nothing able to emit it (BACKLOG.md item 4), so a genuine
                    // execution failure had no way to be reported — it either threw a 500 or,
                    // worse, reported `completed`. Summarising calls a language model over
                    // the network; it can fail for reasons that are nobody's bug.
                    log.error("action.summarize.failed actionId={} documentId={}",
                            request.actionId(), p.documentId(), failure);
                    // The reason reaches the user. Previously the card said "Action
                    // rejected" — the one thing that had definitively not happened.
                    return ActionResult.failed(request.actionId(), request.type(),
                            "This document could not be summarised: nothing in it was "
                                    + "relevant enough to summarise.");
                }

            } else if (request.type() == ActionType.LOOKUP_KNOWLEDGE
                    && request.payload() instanceof LookupPayload p) {
                try {
                    resultData = lookUp(p, userId);
                } catch (Exception failure) {
                    log.error("action.lookup.failed actionId={}", request.actionId(), failure);
                    return ActionResult.failed(request.actionId(), request.type(),
                            "The lookup could not be completed.");
                }
            }
        }

        // 4. Return the contracted shape: execution status, not the decision echoed back
        ActionStatus status = request.decision() == ActionDecision.approved
                ? ActionStatus.completed
                : ActionStatus.rejected;
        // APPROVED BUT NOTHING HAPPENED is its own failure, and it used to report
        // `completed`. If the payload does not match the type the branches above do
        // nothing, the audit says approved, and the user is told it worked — which is the
        // shape of the reported bug: the audit and the UI disagreeing about one click.
        if (request.decision() == ActionDecision.approved && resultData == null) {
            log.error("action.no_effect actionId={} type={} payload={} — approved but no "
                            + "branch executed", request.actionId(), request.type(),
                    request.payload() == null ? "null" : request.payload().getClass().getSimpleName());
            return ActionResult.failed(request.actionId(), request.type(),
                    "This action was approved but could not be carried out.");
        }

        return new ActionResult(request.actionId(), status, request.type(), resultData, null);
    }

    /**
     * Produces a real document summary, which is what Day 11's "done when" asks for.
     *
     * <p>Reuses {@code POST /answer} rather than adding a summarise endpoint. Asking the
     * existing grounded-answer path to summarise ONE document gets the whole apparatus for
     * free: the allow-list is enforced the same way, the answer is checked against the
     * retrieved text by the grounding guard, and an unanswerable request comes back as
     * insufficient_context instead of an invention.
     *
     * <p><strong>Ownership is re-checked here, not trusted from the payload.</strong> The
     * request arrives from a browser and names a documentId; taking that at face value would
     * let anyone summarise any document by editing a request. The document must be owned by
     * the caller AND ready, which is the same rule that builds allowed_document_ids.
     */
    private SummarizeResult summarise(SummarizePayload payload, UUID userId) {
        Document document = documentRepository.findById(payload.documentId())
                .filter(d -> d.getOwner() != null && userId.equals(d.getOwner().getId()))
                .filter(d -> d.getStatus() == DocumentStatus.ready)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Document not available to summarise: " + payload.documentId()));

        GenAiAnswerResponse response = genAiClient.answer(
                SUMMARISE_QUESTION,
                // Exactly one document. A summary of "this document" must not quietly draw
                // on every other document the user owns.
                List.of(document.getId()),
                null,
                List.of(),
                // Summarising always uses the configured default. A tool execution is not a
                // place to offer a privacy choice the user cannot see at approval time.
                null);

        if (response.isInsufficientContext() || response.answer() == null
                || response.answer().isBlank()) {
            // The document has no chunks, or nothing in it cleared the relevance floor.
            // Saying so beats returning an empty string the UI would render as a blank card.
            throw new IllegalStateException(
                    "No summarisable content for document " + document.getId());
        }
        // Wrapped, not bare. The frontend renders `result.summary`, and returning the
        // string on its own made that expression `undefined` — an approved summary showed
        // as an empty card with no error anywhere. See SummarizeResult.
        return new SummarizeResult(response.answer());
    }

    /**
     * Executes an approved {@code lookup-knowledge}: searches the caller's documents and
     * returns the passages that matched.
     *
     * <p><strong>This branch used to be a lie, then an admitted gap, and is now
     * implemented.</strong> It returned "Placeholder logic: Queried knowledge base." and
     * reported {@code completed} — the UI told the user an action had succeeded when nothing
     * had run. Day 11 replaced that with an honest {@code failed}, because a confident false
     * success is worse than an admitted gap. Day 14b has to go further: the GenAI service now
     * PROPOSES this tool, and proposing an action that can only ever fail is worse than
     * never offering it.
     *
     * <p>Searches EVERY ready document the caller owns, which is the difference from the
     * chat turn that proposed it — the tool exists for "search my documents for X" when the
     * answer in front of the user did not cover it.
     *
     * <p>Returns the SENTENCES, not a generated answer. A lookup is a retrieval operation,
     * and the honest result is the located text — Spring reads it from the chunk rows it
     * wrote rather than echoing whatever the service sent back.
     */
    private LookupResult lookUp(LookupPayload payload, UUID userId) {
        List<UUID> allowed = documentRepository
                .findByOwner_IdAndStatusOrderByUploadDateDesc(userId, DocumentStatus.ready)
                .stream()
                .map(Document::getId)
                .toList();

        GenAiAnswerResponse response = genAiClient.answer(
                payload.query(), allowed, null, List.of(), null);

        List<String> snippets = new java.util.ArrayList<>();
        if (response.citations() != null) {
            Map<UUID, DocumentChunk> chunks = documentChunkRepository
                    .findByIdIn(response.citations().stream().map(GenAiCitation::chunkId).toList())
                    .stream()
                    .collect(Collectors.toMap(DocumentChunk::getId, chunk -> chunk));
            for (GenAiCitation citation : response.citations()) {
                DocumentChunk chunk = chunks.get(citation.chunkId());
                if (chunk == null) {
                    log.warn("lookup cited chunk {} which no longer exists", citation.chunkId());
                    continue;
                }
                snippets.add((citation.quote() == null || citation.quote().isBlank())
                        ? chunk.getText()
                        : citation.quote());
            }
        }
        if (snippets.isEmpty()) {
            // Nothing matched. FAILED would be wrong — the search ran and completed; it
            // simply found nothing, which is a result a user can act on. An empty list is
            // what the published shape expresses, and the UI reads snippets[0].
            log.info("action.lookup.no_matches query_length={}", payload.query().length());
        }
        return new LookupResult(List.copyOf(snippets));
    }

    @Transactional(readOnly = true)
    public PageResponse<ActionAuditDto> getAuditTrail(UUID userId, Pageable pageable) {
        return PageResponse.from(
                actionAuditRepository.findByOwnerOrderByCreatedAtDesc(userId, pageable),
                ActionAuditDto::from);
    }
}
