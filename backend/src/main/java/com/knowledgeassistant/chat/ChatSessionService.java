package com.knowledgeassistant.chat;

import com.knowledgeassistant.user.User;
import com.knowledgeassistant.chat.dto.ActionProposalDto;
import com.knowledgeassistant.chat.dto.ChatSessionDto;
import com.knowledgeassistant.chat.dto.MessageDto;
import com.knowledgeassistant.chat.dto.CitationDto;
import com.knowledgeassistant.chat.dto.MessageRequest;
import com.knowledgeassistant.citation.Citation;
import com.knowledgeassistant.genai.dto.GenAiTrace;
import com.knowledgeassistant.citation.CitationRepository;
import com.knowledgeassistant.document.Document;
import com.knowledgeassistant.document.DocumentChunk;
import com.knowledgeassistant.document.DocumentChunkRepository;
import com.knowledgeassistant.document.DocumentRepository;
import com.knowledgeassistant.genai.GenAiClient;
import com.knowledgeassistant.genai.dto.GenAiAnswerResponse;
import com.knowledgeassistant.genai.dto.GenAiCitation;
import com.knowledgeassistant.genai.dto.GenAiTurn;
import com.knowledgeassistant.genai.GenAiProperties;
import com.knowledgeassistant.document.DocumentStatus;
import com.knowledgeassistant.common.ChatNotFoundException;
import com.knowledgeassistant.common.dto.PageResponse;
import org.springframework.transaction.support.TransactionTemplate;
import jakarta.persistence.EntityManager;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class ChatSessionService {

    private static final Logger log = LoggerFactory.getLogger(ChatSessionService.class);

    /**
     * What the user reads when retrieval found nothing above the relevance threshold.
     *
     * <p>The service returns {@code outcome=insufficient_context} with an EMPTY answer, on
     * purpose: whether there is enough context is decided in code from retrieval scores
     * before the model is ever called, so the model is never asked to invent a way of saying
     * "I don't know". Turning that empty string into a sentence is Spring's job — an empty
     * chat bubble is not "a clear insufficient-context response".
     */
    private static final String NO_ANSWER_REPLY =
            "I couldn't find anything in your documents that answers that. "
                    + "Try rephrasing, or upload a document that covers it.";

    /**
     * How close a rejected passage has to be before the reply says so, rather than telling
     * the user their library is missing something.
     *
     * <p>0.08 below the floor, which on the measured corpus separates the two cases the old
     * copy conflated. A misspelling lands around 0.53-0.55 against a 0.60 floor; a subject
     * the documents genuinely do not cover lands far lower, or matches nothing at all.
     *
     * <p>Not tuned to a target. It is wide enough to catch the reported case with room, and
     * narrow enough that "upload a document" is still said when that really is the advice.
     */
    private static final double NEAR_MISS_BAND = 0.08;

    /**
     * What the user reads when retrieval found nothing, chosen from how close it came.
     *
     * <p><strong>The old copy blamed the documents for a problem in the typing.</strong>
     * Reported from real use: <em>"tell me about ai saftey"</em> returned "I couldn't find
     * anything in your documents… upload a document that covers it" while AI_safety.pdf sat
     * in the corpus with 81 chunks. The misspelling scores 0.5355 against a 0.60 floor; the
     * correct spelling scores 0.7120. One letter, and the advice pointed at the wrong thing
     * — there was nothing to upload.
     *
     * <p>The service always knew the near miss had happened. It simply had no way to say so,
     * because a total miss and a near miss produced identical text.
     */
    private static String noAnswerReply(GenAiTrace trace) {
        if (trace == null || trace.bestRejectedScore() == null || trace.minScore() == null) {
            return NO_ANSWER_REPLY;
        }
        double best = trace.bestRejectedScore();
        double floor = trace.minScore();
        if (best < floor - NEAR_MISS_BAND) {
            // Genuinely nothing like it. The original advice is the right advice.
            return NO_ANSWER_REPLY;
        }
        // Close. Say so, and name the likeliest cause rather than sending them to upload
        // something they already have.
        return "Nothing in your documents quite matched that — the closest passage came in "
                + "just under the relevance threshold. This is often a typo or a difference "
                + "in wording. Try rephrasing it, or check the spelling.";
    }

    /**
     * Grounded retrieval, but the model produced nothing usable.
     *
     * <p>Deliberately worded differently from {@link #NO_ANSWER_REPLY}. The documents DID
     * cover the question — retrieval cleared the threshold — and the generation step failed.
     * Telling the user their documents do not cover it would be false, and collapsing the two
     * would hide a model failure behind a corpus explanation.
     */
    /**
     * What the user reads when the request is one this assistant cannot serve.
     *
     * <p>Deliberately NOT {@link #NO_ANSWER_REPLY}. Telling someone their documents do not
     * cover "send an email to the maintenance team" is a false explanation — the documents
     * are not the reason, and it invites them to rephrase or upload something, which cannot
     * help. Day 12's requirement is that the service "explains limitations clearly", and a
     * clear explanation names the limitation.
     */
    private static final String UNSUPPORTED_REPLY_PREFIX =
            "I can't do that — this assistant answers questions about your documents and "
                    + "cannot ";

    private static final String EMPTY_ANSWER_REPLY =
            "I found relevant passages in your documents but couldn't put together an answer. "
                    + "Please try asking again.";

    /**
     * WHERE THE KEYWORD ROUTER USED TO BE. Day 14b deleted it from here.
     *
     * <p>Three lists lived at this spot — QUESTION_OPENERS, TASK_TRIGGERS and
     * TITLE_PREFIXES — plus the two methods that read them. They have moved to
     * {@code genai-service/app/intent.py}, which is the only side of the system holding a
     * sentence encoder and therefore the only side that can run a CLASSIFIER rather than
     * match strings somebody thought of in advance.
     *
     * <p>Moved, not copied: keeping a second copy here is the exact failure this project
     * keeps finding. Two of those lists had to agree and silently stopped agreeing —
     * "note down" was in TITLE_PREFIXES and not in TASK_TRIGGERS, so the system knew how
     * to extract a title from a phrasing it would never route, and nothing noticed for
     * four days. A {@code benchmarks/22} script reimplemented the same rules a third time
     * in Python with a comment admitting it was a copy, which is a note rather than a
     * mechanism.
     *
     * <p>Measured on the Day 14 held-out set before the move, in
     * {@code benchmarks/23_intent_classifier.py}: these keyword rules scored 25/27, the
     * classifier alone 24/27, and the two together 26/27 — all three with zero false
     * positives. The rules were NOT replaced, because they are still the better half for
     * create-task and a readable rule should decide where it applies; they were relocated
     * so that one language owns them. {@code app.intent} asks the triggers first and
     * consults the classifier only where they stay silent.
     *
     * <p>What remains on this side is TRANSLATION, in {@link ActionProposer} — turning a
     * document id into a filename and re-checking that the caller may see it, which needs
     * the {@code documents} table and so could never have lived in Python.
     */
    private final ChatSessionRepository chatSessionRepository;
    private final MessageRepository messageRepository;
    private final CitationRepository citationRepository;
    private final DocumentRepository documentRepository;
    private final DocumentChunkRepository documentChunkRepository;
    private final GenAiClient genAiClient;
    private final GenAiProperties genAiProperties;
    private final TransactionTemplate transactionTemplate;
    private final EntityManager entityManager;
    private final ActionProposer actionProposer;

    public ChatSessionService(ChatSessionRepository chatSessionRepository,
                              MessageRepository messageRepository,
                              CitationRepository citationRepository,
                              DocumentRepository documentRepository,
                              DocumentChunkRepository documentChunkRepository,
                              GenAiClient genAiClient,
                              GenAiProperties genAiProperties,
                              TransactionTemplate transactionTemplate,
                              EntityManager entityManager,
                              ActionProposer actionProposer) {
        this.chatSessionRepository = chatSessionRepository;
        this.messageRepository = messageRepository;
        this.citationRepository = citationRepository;
        this.documentRepository = documentRepository;
        this.documentChunkRepository = documentChunkRepository;
        this.genAiClient = genAiClient;
        this.genAiProperties = genAiProperties;
        this.transactionTemplate = transactionTemplate;
        this.entityManager = entityManager;
        this.actionProposer = actionProposer;
    }

    /**
     * Loads the citations for a page of messages, keyed by message.
     *
     * <p>One query for the whole page rather than one per message.
     */
    private Map<UUID, List<CitationDto>> citationsFor(List<Message> messages) {
        if (messages.isEmpty()) {
            return Map.of();
        }

        List<UUID> ids = messages.stream().map(Message::getId).toList();

        return citationRepository.findByMessageIdInOrderByCreatedAtAsc(ids).stream()
                .collect(Collectors.groupingBy(
                        Citation::getMessageId,
                        Collectors.mapping(CitationDto::from, Collectors.toList())));
    }

    /**
     * Turns the GenAI service's citations into rows the frontend can already render.
     *
     * <p>This replaced a placeholder that picked a document by
     * {@code Math.floorMod(query.hashCode(), candidates.size())}. That was honest while the
     * ANSWER was also a placeholder — both said so. Pairing a real RAG answer with a
     * hash-picked source would have been the opposite: confident misattribution, which is
     * precisely what qa-v2, quote-resolved citations and dropping ambiguous matches were all
     * built to prevent. It would have undone Month 3's central design decision at the last hop.
     *
     * <p>The service returns {@code chunk_id} and no text. The excerpt and section are read
     * back from {@code document_chunks} here, because Spring wrote those rows and should not
     * take a service's word for their contents.
     *
     * <p><strong>No citations means no rows.</strong> An uncited answer is honest; a wrongly
     * cited one is not. Day 7 measured citations resolving roughly 1 in 3 — the model
     * paraphrases instead of quoting, and an unresolvable quote is dropped rather than
     * guessed at — so empty here is a normal, expected state, not a failure to paper over.
     */
    private List<CitationDto> persistCitations(UUID assistantMessageId,
                                               List<GenAiCitation> cited,
                                               Instant now) {
        if (cited == null || cited.isEmpty()) {
            return List.of();
        }

        // One query for every cited chunk rather than one per citation.
        Map<UUID, DocumentChunk> chunks = documentChunkRepository
                .findByIdIn(cited.stream().map(GenAiCitation::chunkId).toList())
                .stream()
                .collect(Collectors.toMap(DocumentChunk::getId, chunk -> chunk));

        List<CitationDto> saved = new ArrayList<>();
        for (GenAiCitation citation : cited) {
            DocumentChunk chunk = chunks.get(citation.chunkId());
            if (chunk == null) {
                // The service cited a chunk this database does not have. Not fatal and not
                // silently dropped either: it means the two sides disagree about the corpus,
                // which is worth a log line and worth NOT rendering as a source.
                log.warn("genai cited chunk {} which no longer exists; skipping", citation.chunkId());
                continue;
            }
            // The SENTENCE the answer rested on, not the whole chunk. Chunks average 1,538
            // characters and reach 2,597 — a card showing that is a dump, not something a
            // reader can inspect. The service locates the sentence within the chunk it
            // already stored here; if it could not, fall back to the full text rather than
            // show nothing.
            String excerpt = (citation.quote() == null || citation.quote().isBlank())
                    ? chunk.getText()
                    : citation.quote();

            saved.add(CitationDto.from(citationRepository.save(new Citation(
                    assistantMessageId,
                    entityManager.getReference(Document.class, chunk.getDocumentId()),
                    chunk.getSection(),
                    excerpt,
                    now,
                    chunk.getId(),
                    chunk.getPage(),
                    (float) citation.score()))));
        }
        return saved;
    }

    @Transactional(readOnly = true)
    public PageResponse<ChatSessionDto> getUserSessions(UUID userId, Pageable pageable) {
        return PageResponse.from(
                chatSessionRepository.findByUser_IdOrderByUpdatedAtDesc(userId, pageable),
                ChatSessionDto::from);
    }

    @Transactional(readOnly = true)
    public List<MessageDto> getSessionMessages(UUID sessionId, UUID userId) {
        // Ownership is part of the existence check: someone else's session simply
        // "does not exist" as far as this caller is concerned.
        if (!chatSessionRepository.existsByIdAndUser_Id(sessionId, userId)) {
            throw new ChatNotFoundException("Chat session not found: " + sessionId);
        }

        List<Message> messages = messageRepository.findBySessionIdOrderByCreatedAtAsc(sessionId);
        Map<UUID, List<CitationDto>> citations = citationsFor(messages);

        // Citations are persisted, so history keeps its sources; action proposals are
        // ephemeral by design and are not replayed.
        return messages.stream()
                .map(message -> MessageDto.from(message, citations.get(message.getId())))
                .collect(Collectors.toList());
    }

    /**
     * Sends a message and returns the assistant's reply.
     *
     * <p><strong>Deliberately NOT {@code @Transactional}.</strong> Answering takes 30-58
     * seconds of CPU generation, and a transaction here would hold a pooled database
     * connection for that entire time. HikariCP defaults to ten connections and nothing in
     * {@code application.properties} raises it, so the eleventh concurrent chat would block
     * on connection acquisition while ten threads sat waiting on an HTTP socket — an outage
     * caused by a keyword, not by load.
     *
     * <p>So the turn is split in three: persist the user's message (transaction), call the
     * AI (<em>no</em> transaction, no connection held), persist the reply (transaction). The
     * cost of the split is that a crash between phases leaves a user message with no reply,
     * which is visibly incomplete and recoverable. The cost of not splitting is a deadlocked
     * connection pool, which is neither.
     *
     * <p><strong>No {@code @Transactional} annotation at all, and the class carries none
     * either.</strong> It used to: {@code @Transactional(readOnly = true)} sat on the CLASS
     * and therefore applied to every public method, so removing the method-level annotation
     * did not take this method out of a transaction — it made it a read-only one, the
     * {@link org.springframework.transaction.support.TransactionTemplate} phases JOINED that
     * outer transaction instead of opening their own, and a connection was held across the
     * whole model call exactly as before. The blanket annotation is gone and the two read
     * methods declare {@code readOnly} for themselves.
     *
     * <p>{@code Propagation.NOT_SUPPORTED} was tried first and is the wrong instrument: it
     * SUSPENDS any surrounding transaction, which also suspends a test-managed one, so every
     * {@code @Transactional} test suddenly could not see its own uncommitted fixtures. No
     * annotation is better — in production nothing is active so the phases open their own,
     * and in a test the phases join the test's transaction and still roll back.
     *
     * <p>Every other chat test was {@code @Transactional} and therefore structurally unable to
     * notice: a test-managed transaction wraps the call, the service joins it, and the suite
     * goes green on a boundary that does not exist. {@code ChatTransactionBoundaryTest} is not
     * {@code @Transactional} for that reason, and it failed before this line was written.
     *
     */
    public MessageDto sendMessage(MessageRequest request, UUID userId) {
        PendingTurn turn = inTransaction(() -> {
            // One query that is both the 404 check and the authorization check — an unowned
            // session never loads.
            ChatSession session = chatSessionRepository.findByIdAndUser_Id(request.sessionId(), userId)
                    .orElseThrow(() -> new ChatNotFoundException(
                            "Chat session not found: " + request.sessionId()));
            return beginTurn(session, request.content(), request.model());
        });

        GenAiAnswerResponse answer = ask(turn, userId);

        return inTransaction(() -> completeTurn(turn, answer, userId));
    }

    /** A user turn that has been persisted and is waiting on an answer. */
    private record PendingTurn(UUID sessionId, UUID questionMessageId, String question,
                               Instant startedAt, String model) {}

    /** Phase 1: the user's message is durable before anything slow is attempted. */
    private PendingTurn beginTurn(ChatSession session, String content, String model) {
        Instant now = Instant.now();
        Message saved = messageRepository.save(
                new Message(session.getId(), content, MessageSender.user, now));
        // The id is carried so history can EXCLUDE this turn: it was persisted a moment ago
        // and is the question being asked, not context for it. Sending it would put the same
        // sentence in the prompt twice.
        return new PendingTurn(session.getId(), saved.getId(), content, now, model);
    }

    /**
     * Phase 2: the slow call. No transaction, no database connection held.
     *
     * <p>{@code allowedDocumentIds} is the caller's own {@code ready} documents — owned AND
     * ready, computed here because Spring is the only side that knows it. It is passed
     * through <strong>unconditionally</strong>, including when empty: there is no "skip the
     * call if the list is empty" branch, because that is the same {@code if} that would let
     * an empty allow-list mean "search everything" on the other side. An empty list costs
     * about 37ms and comes back {@code insufficient_context} without the model ever loading.
     */
    private GenAiAnswerResponse ask(PendingTurn turn, UUID userId) {
        List<UUID> allowedDocumentIds = documentRepository
                .findByOwner_IdAndStatusOrderByUploadDateDesc(userId, DocumentStatus.ready)
                .stream()
                .map(Document::getId)
                .toList();

        return genAiClient.answer(turn.question(), allowedDocumentIds, turn.sessionId(),
                recentHistory(turn), turn.model());
    }

    /**
     * The last few turns of this conversation, oldest first, excluding the question itself.
     *
     * <p>Spring sends these because Spring owns the {@code messages} table. The alternative —
     * letting Python look them up from {@code session_id} — would break rule R1 (that service
     * holds SELECT on the chunk tables and nothing else) and would make an answer depend on
     * state outside its own request, which is what keeps a bad answer reproducible today.
     *
     * <p>Capped at {@code app.genai.history-turns}. Prefill runs at ~280 tokens/s, so an
     * uncapped conversation would add latency to every request forever.
     */
    private List<GenAiTurn> recentHistory(PendingTurn turn) {
        List<Message> messages = messageRepository.findBySessionIdOrderByCreatedAtAsc(turn.sessionId());

        List<GenAiTurn> turns = messages.stream()
                .filter(m -> !m.getId().equals(turn.questionMessageId()))
                .map(m -> new GenAiTurn(m.getSender().name(), m.getContent()))
                .toList();

        int from = Math.max(0, turns.size() - genAiProperties.historyTurns());
        return turns.subList(from, turns.size());
    }

    /** Phase 3: persist the reply and its sources. */
    private MessageDto completeTurn(PendingTurn turn, GenAiAnswerResponse answer, UUID userId) {
        Instant now = Instant.now();
        ChatSession session = chatSessionRepository.findById(turn.sessionId())
                .orElseThrow(() -> new ChatNotFoundException("Chat session not found: " + turn.sessionId()));

        String unsupported = answer.trace() == null ? null : answer.trace().unsupportedRequest();

        String reply;
        if (unsupported != null) {
            // Names the capability, so the user learns what this product is rather than
            // being sent to rephrase a question that can never work.
            reply = UNSUPPORTED_REPLY_PREFIX + unsupported + ".";
        } else if (answer.isInsufficientContext()) {
            reply = noAnswerReply(answer.trace());
        } else {
            reply = answer.answer();
        }
        if (reply == null || reply.isBlank()) {
            // Grounded retrieval, empty generation. Day 7 keeps those distinguishable on
            // purpose — the documents DID cover it and the model failed — but the user still
            // needs a sentence rather than an empty bubble.
            reply = EMPTY_ANSWER_REPLY;
        }

        Message aiMessage = messageRepository.save(
                new Message(session.getId(), reply, MessageSender.assistant, now));

        List<CitationDto> citations = answer.isInsufficientContext()
                ? List.of()
                : persistCitations(aiMessage.getId(), answer.citations(), now);
        // Translated, not decided. Which tool a message asks for is decided by the GenAI
        // service, which holds the encoder; ActionProposer turns its answer into something
        // the frontend and the audit flow can read, and drops anything it cannot make safe.
        List<ActionProposalDto> proposals = actionProposer.translate(answer.proposals(), userId);

        session.setUpdatedAt(now);
        session.setLastMessagePreview(reply.length() > 100 ? reply.substring(0, 97) + "..." : reply);
        chatSessionRepository.save(session);

        // The user asked one thing and the service searched for another. Telling them is
        // not optional: answering "ai saftey" as "ai safety" without saying so substitutes
        // their question for a different one. Empty on every normally-retrieved answer.
        List<MessageDto.SpellingCorrectionDto> corrections =
                answer.trace() == null || answer.trace().spellingCorrections() == null
                        ? List.of()
                        : answer.trace().spellingCorrections().stream()
                                .map(c -> new MessageDto.SpellingCorrectionDto(c.typed(), c.used()))
                                .toList();

        return MessageDto.from(aiMessage, citations, proposals, corrections);
    }

    /** Runs a unit of work in its own transaction, so the slow call can sit outside one. */
    private <T> T inTransaction(java.util.function.Supplier<T> work) {
        return transactionTemplate.execute(status -> work.get());
    }

    /**
     * Opens a conversation with its first message.
     *
     * <p>Not {@code @Transactional}, for the reason given on {@link #sendMessage} — and it
     * takes the same three phases, so the opening turn gets real answers and real citations
     * exactly like every later one. That equivalence was already load-bearing: this path and
     * {@code sendMessage} were once separate copies, and the copy behind "new chat" was
     * missing the action-proposal branch, so the first message of a conversation could never
     * propose a task while every later one could.
     *
     * <p>Carries no transaction annotation, for the reason set out on {@link #sendMessage}.
     */
    public ChatSessionDto createSession(UUID userId, String initialMessage, String model) {
        PendingTurn turn = inTransaction(() -> {
            Instant now = Instant.now();
            String title = initialMessage.length() > 50
                    ? initialMessage.substring(0, 47) + "..."
                    : initialMessage;

            User userProxy = entityManager.getReference(User.class, userId);
            ChatSession session = chatSessionRepository.save(
                    new ChatSession(userProxy, title, now, now, null));

            return beginTurn(session, initialMessage, model);
        });

        GenAiAnswerResponse answer;
        try {
            answer = ask(turn, userId);
        } catch (RuntimeException e) {
            // Phase 1 has already COMMITTED the session and the user's question, which is
            // what lets the model call run without holding a pooled connection. The cost is
            // that a failed answer leaves a conversation containing a question and no reply.
            //
            // That is not merely untidy. The client stays on /chat/new until a session id
            // comes back, so every retry posts here again and creates ANOTHER one: eight
            // 503s from the GenAI service produced eight identical conversations in the
            // sidebar, none of which the user had asked for. Undo phase 1 before the failure
            // propagates. Deleting the session cascades to the message just written.
            //
            // sendMessage deliberately does NOT do this: there the session predates the turn
            // and belongs to the user, so removing it would destroy their history.
            inTransaction(() -> {
                chatSessionRepository.deleteById(turn.sessionId());
                return null;
            });
            throw e;
        }

        return inTransaction(() -> {
            MessageDto initialResponse = completeTurn(turn, answer, userId);
            ChatSession session = chatSessionRepository.findById(turn.sessionId())
                    .orElseThrow(() -> new ChatNotFoundException(
                            "Chat session not found: " + turn.sessionId()));
            return ChatSessionDto.from(session, initialResponse);
        });
    }

    /**
     * Deletes a session the caller owns. Messages, tasks, and audit rows follow via the
     * ON DELETE CASCADE foreign keys declared back on Day 3.
     */
    @Transactional
    public void deleteSession(UUID sessionId, UUID userId) {
        ChatSession session = chatSessionRepository.findByIdAndUser_Id(sessionId, userId)
                .orElseThrow(() -> new ChatNotFoundException("Chat session not found: " + sessionId));

        chatSessionRepository.delete(session);
    }
}