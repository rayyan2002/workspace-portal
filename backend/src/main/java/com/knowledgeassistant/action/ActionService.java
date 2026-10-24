package com.knowledgeassistant.action;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import tools.jackson.databind.ObjectMapper;
import com.knowledgeassistant.action.dto.ActionRequest;
import com.knowledgeassistant.action.dto.ActionResult;
import com.knowledgeassistant.action.dto.CreateTaskPayload;
import com.knowledgeassistant.action.dto.LookupPayload;
import com.knowledgeassistant.action.dto.LookupResult;
import com.knowledgeassistant.action.dto.SummarizePayload;
import com.knowledgeassistant.action.dto.SummarizeResult;
import com.knowledgeassistant.action.dto.ActionAuditDto;
import com.knowledgeassistant.chat.ChatSessionRepository;
import com.knowledgeassistant.common.ChatNotFoundException;
import com.knowledgeassistant.common.dto.PageResponse;
import com.knowledgeassistant.document.Document;
import com.knowledgeassistant.document.DocumentChunk;
import com.knowledgeassistant.document.DocumentChunkRepository;
import com.knowledgeassistant.document.DocumentRepository;
import com.knowledgeassistant.document.DocumentStatus;
import com.knowledgeassistant.genai.GenAiClient;
import com.knowledgeassistant.genai.dto.GenAiAnswerResponse;
import com.knowledgeassistant.genai.dto.GenAiCitation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import com.knowledgeassistant.task.Task;
import com.knowledgeassistant.task.TaskRepository;
import com.knowledgeassistant.task.TaskStatus;
import com.knowledgeassistant.task.dto.TaskDto;
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
    private final ActionProposalRepository actionProposalRepository;
    private final DocumentRepository documentRepository;
    private final DocumentChunkRepository documentChunkRepository;
    private final GenAiClient genAiClient;
    private final TransactionTemplate transactionTemplate;
    private final ObjectMapper objectMapper;
    /**
     * The interface, not ThreadPoolTaskExecutor. Tests substitute a synchronous executor:
     * they run inside a rolled-back transaction, so a real background thread could not see
     * the audit row the request has not committed yet. Running inline keeps the assertion
     * about WHAT was recorded rather than about thread timing.
     */
    private final TaskExecutor actionExecutor;

    public ActionService(ChatSessionRepository chatSessionRepository,
                         ActionAuditRepository actionAuditRepository,
                         TaskRepository taskRepository,
                         ActionProposalRepository actionProposalRepository,
                         DocumentRepository documentRepository,
                         DocumentChunkRepository documentChunkRepository,
                         GenAiClient genAiClient,
                         TransactionTemplate transactionTemplate,
                         ObjectMapper objectMapper,
                         @Qualifier("actionExecutor") TaskExecutor actionExecutor) {
        this.chatSessionRepository = chatSessionRepository;
        this.actionAuditRepository = actionAuditRepository;
        this.taskRepository = taskRepository;
        this.actionProposalRepository = actionProposalRepository;
        this.documentRepository = documentRepository;
        this.documentChunkRepository = documentChunkRepository;
        this.genAiClient = genAiClient;
        this.transactionTemplate = transactionTemplate;
        this.objectMapper = objectMapper;
        this.actionExecutor = actionExecutor;
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
            log.info("action.repeat actionId={} firstDecision={} storedStatus={} — "
                            + "not executed again",
                    request.actionId(), first.getDecision(), first.getStatus());

            // V21: REPLAY THE REAL OUTCOME. Approving a summarize takes about two minutes
            // (134.9s measured), so a user who navigated away mid-request used to lose the
            // work permanently — the server finished, nothing kept the answer, and coming
            // back produced a shrug. The answer is kept now, so a second click returns it.
            //
            // Status comes from the ROW, not from the decision. Inferring it was a second
            // bug: an approved action that FAILED replayed as a success.
            if (first.getStatus() != null) {
                return new ActionResult(
                        request.actionId(), first.getStatus(), request.type(),
                        readResult(first), first.getFailureReason(),
                        // What actually stands, so the card can stop reporting a replay as
                        // though this click caused it.
                        first.getDecision());
            }

            // Decided before V21, so there is genuinely nothing stored. No backfill would
            // be anything but an invention, and claiming a summary we never kept is worse
            // than admitting we did not keep it.
            return new ActionResult(
                    request.actionId(),
                    first.getDecision() == ActionDecision.approved
                            ? ActionStatus.completed
                            : ActionStatus.rejected,
                    request.type(), null, null, first.getDecision());
        }

        // 3. ALWAYS write the audit log, regardless of decision — and BEFORE executing.
        //    That ordering was incidental until V20 and is now load-bearing: the UNIQUE
        //    constraint on action_id means a duplicate insert fails here, so the side effect
        //    below never happens.
        ActionAudit audit = transactionTemplate.execute(status -> actionAuditRepository.save(
                new ActionAudit(
                        request.actionId(),
                        request.sessionId(),
                        request.type(),
                        request.decision(),
                        Instant.now()
                )));

        // 3. THE DECISION IS ACKNOWLEDGED NOW; THE WORK MAY NOT BE DONE YET.
        //
        //    Creating a task is instant and a rejection is instant, so those still answer
        //    inside the request. Summarising and lookup are not: they run a full
        //    grounded-answer pass over a language model, measured at 78-135 seconds. Running
        //    that inside POST /api/ai/actions meant the human's own decision was not
        //    acknowledged until the work finished, so the card sat on a spinner long enough
        //    that people navigated away — and before V21 that destroyed the work.
        //
        //    Returning `running` is not a weaker answer than `completed`. It is the true
        //    one: the decision is recorded, the side effect is accepted, and the audit row
        //    says so from this moment rather than two minutes later.
        if (request.decision() == ActionDecision.approved && isSlow(request.type())) {
            record(request.actionId(), ActionStatus.running, null, null);
            actionExecutor.execute(() -> runInBackground(request, userId));
            log.info("action.accepted actionId={} type={} — running in the background",
                    request.actionId(), request.type());
            return new ActionResult(request.actionId(), ActionStatus.running,
                    request.type(), null, null, null);
        }

        // 4. EXECUTE side-effects ONLY if approved
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
                // V23: which action produced this task, so the Actions page can link to the
                // prompt that proposed it rather than to the conversation as a whole.
                task.setSourceActionId(request.actionId());
                transactionTemplate.execute(status -> taskRepository.save(task));
                resultData = TaskDto.from(task);

            }
            // SUMMARIZE_DOCUMENT and LOOKUP_KNOWLEDGE used to be handled here and are not
            // any more: both call a language model and are answered with `running` above,
            // then finished by runInBackground. Leaving dead branches behind would invite
            // the next reader to "fix" the slow path by re-enabling them.
        }

        // 5. Return the contracted shape: execution status, not the decision echoed back
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
            return record(audit, ActionResult.failed(request.actionId(), request.type(),
                    "This action was approved but could not be carried out."));
        }

        return record(audit,
                new ActionResult(request.actionId(), status, request.type(), resultData,
                        null, null));
    }

    /**
     * Stores what execution produced, then returns it unchanged.
     *
     * <p>Every exit from {@code processAction} goes through here, so "the row records the
     * outcome" is a property of the control flow rather than something each branch has to
     * remember. A branch that forgot would reintroduce exactly the bug V21 exists to fix.
     *
     * <p>A failure to SERIALISE must not turn a completed action into a failed one. The
     * work really happened; losing the ability to replay it is a smaller harm than telling
     * the user it did not occur, so this logs and returns the live result either way.
     */
    private ActionResult record(ActionAudit audit, ActionResult result) {
        String json = null;
        if (result.status() == ActionStatus.completed && result.result() != null) {
            try {
                json = objectMapper.writeValueAsString(result.result());
            } catch (Exception serialisation) {
                log.error("action.result.unstorable actionId={} type={} — the action "
                                + "succeeded but its result cannot be replayed",
                        result.actionId(), result.type(), serialisation);
            }
        }
        record(result.actionId(), result.status(), json, result.failureReason());
        return result;
    }

    /**
     * Writes the outcome onto the audit row, by action id.
     *
     * <p>BY ID RATHER THAN BY ENTITY, because the background thread that finishes a slow
     * action does not share the request's persistence context. Handing a detached entity
     * across that boundary is how you get a silent no-op or a stale overwrite; re-reading
     * inside the transaction is cheap and cannot.
     */
    private void record(String actionId, ActionStatus status, String resultJson,
                        String failureReason) {
        transactionTemplate.execute(tx -> actionAuditRepository.findByActionId(actionId)
                .map(row -> {
                    row.recordOutcome(status, resultJson, failureReason);
                    return actionAuditRepository.save(row);
                })
                .orElseGet(() -> {
                    log.error("action.audit.missing actionId={} — outcome {} cannot be "
                            + "recorded", actionId, status);
                    return null;
                }));
    }

    /** True for work that calls a language model, which is measured in minutes. */
    private boolean isSlow(ActionType type) {
        return type == ActionType.SUMMARIZE_DOCUMENT || type == ActionType.LOOKUP_KNOWLEDGE;
    }

    /**
     * Runs an already-approved, already-audited slow action and records what it produced.
     *
     * <p>Nothing is returned to anyone: the caller was answered when the decision was
     * recorded. The only output is the audit row, which is why every path here writes one —
     * a `running` row that never resolves is the single state with no honest reading.
     */
    private void runInBackground(ActionRequest request, UUID userId) {
        try {
            Object resultData = null;
            if (request.type() == ActionType.SUMMARIZE_DOCUMENT
                    && request.payload() instanceof SummarizePayload p) {
                resultData = summarise(p, userId);
            } else if (request.type() == ActionType.LOOKUP_KNOWLEDGE
                    && request.payload() instanceof LookupPayload p) {
                resultData = lookUp(p, userId);
            }

            if (resultData == null) {
                log.error("action.no_effect actionId={} type={} — approved but no branch ran",
                        request.actionId(), request.type());
                record(request.actionId(), ActionStatus.failed, null,
                        "This action was approved but could not be carried out.");
                return;
            }
            record(request.actionId(), ActionStatus.completed,
                    serialise(request.actionId(), resultData), null);
            log.info("action.finished actionId={} type={}",
                    request.actionId(), request.type());

        } catch (Exception failure) {
            log.error("action.background.failed actionId={} type={}",
                    request.actionId(), request.type(), failure);
            record(request.actionId(), ActionStatus.failed, null,
                    request.type() == ActionType.SUMMARIZE_DOCUMENT
                            ? "This document could not be summarised: nothing in it was "
                              + "relevant enough to summarise."
                            : "The lookup could not be completed.");
        }
    }

    private String serialise(String actionId, Object resultData) {
        try {
            return objectMapper.writeValueAsString(resultData);
        } catch (Exception serialisation) {
            log.error("action.result.unstorable actionId={} — the action succeeded but its "
                    + "result cannot be replayed", actionId, serialisation);
            return null;
        }
    }

    /**
     * Reads a stored result back into the shape the API returns.
     *
     * <p>Deserialised to {@code Object} on purpose: what the caller wants is the JSON it
     * would have received the first time, and routing it back through a typed DTO would let
     * the stored shape drift from the live one with nothing to notice.
     */
    private Object readResult(ActionAudit audit) {
        if (audit.getResult() == null) {
            return null;
        }
        try {
            return objectMapper.readValue(audit.getResult(), Object.class);
        } catch (Exception malformed) {
            log.error("action.result.unreadable actionId={} — stored result will not parse",
                    audit.getActionId(), malformed);
            return null;
        }
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
        var page = actionAuditRepository.findByOwnerOrderByCreatedAtDesc(userId, pageable);

        // ONE extra query for the whole page, not one per row. QueryCountTest guards this
        // path for exactly this reason. Actions decided before V23 have no proposal row and
        // resolve to null, which the frontend reads as "link to the session, not a message".
        Map<String, UUID> messageIds = actionProposalRepository
                .findByActionIdIn(page.getContent().stream()
                        .map(ActionAudit::getActionId).toList())
                .stream()
                .collect(Collectors.toMap(ActionProposal::getActionId,
                        ActionProposal::getMessageId, (a, b) -> a));

        return PageResponse.from(page,
                // The stored result travels with the row, so the Actions page can show what
                // a background action produced without re-running anything.
                audit -> ActionAuditDto.from(audit, readResult(audit),
                        messageIds.get(audit.getActionId())));
    }
}
