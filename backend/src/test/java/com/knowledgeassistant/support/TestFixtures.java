package com.knowledgeassistant.support;

import com.knowledgeassistant.action.ActionAudit;
import com.knowledgeassistant.action.ActionAuditRepository;
import com.knowledgeassistant.action.ActionDecision;
import com.knowledgeassistant.action.ActionType;
import com.knowledgeassistant.chat.ChatSession;
import com.knowledgeassistant.chat.ChatSessionRepository;
import com.knowledgeassistant.chat.Message;
import com.knowledgeassistant.chat.MessageRepository;
import com.knowledgeassistant.chat.MessageSender;
import com.knowledgeassistant.document.Document;
import com.knowledgeassistant.document.DocumentRepository;
import com.knowledgeassistant.document.DocumentStatus;
import com.knowledgeassistant.security.jwt.JwtService;
import com.knowledgeassistant.security.userdetails.UserPrincipal;
import com.knowledgeassistant.task.Task;
import com.knowledgeassistant.task.TaskPriority;
import com.knowledgeassistant.task.TaskRepository;
import com.knowledgeassistant.task.TaskStatus;
import com.knowledgeassistant.user.Role;
import com.knowledgeassistant.user.RoleName;
import com.knowledgeassistant.user.RoleRepository;
import com.knowledgeassistant.citation.Citation;
import com.knowledgeassistant.citation.CitationRepository;
import com.knowledgeassistant.user.User;
import com.knowledgeassistant.user.UserRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * Builds each test its own users and data.
 *
 * <p>Tests used to lean on the seeded demo accounts, which coupled the suite to whatever
 * V8 happened to contain — so retiring those accounts broke 27 tests that were not
 * testing seed data at all. Fixtures created here live inside the test's transaction and
 * roll back with it, so every test starts from a world it fully controls and no test can
 * see another's rows.
 *
 * <p>Emails are randomised because users.email is UNIQUE and the suite would otherwise
 * collide with itself on re-run.
 */
@Component
public class TestFixtures {

    public static final String PASSWORD = "test-password-123";

    private final UserRepository userRepository;
    private final RoleRepository roleRepository;
    private final ChatSessionRepository chatSessionRepository;
    private final MessageRepository messageRepository;
    private final TaskRepository taskRepository;
    private final DocumentRepository documentRepository;
    private final ActionAuditRepository actionAuditRepository;
    private final CitationRepository citationRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final String uploadDir;

    @jakarta.persistence.PersistenceContext
    private jakarta.persistence.EntityManager entityManager;

    /**
     * Users created since the last {@link #cleanUp()}.
     *
     * <p>Most tests are @Transactional and roll back, so this is never needed. A few
     * cannot be — anything asserting on what COMMITS, such as refresh-token reuse
     * detection, is meaningless inside a transaction that will be rolled back. Those
     * tests have to tidy up after themselves, and this is what lets them.
     */
    private final List<UUID> createdUserIds = new ArrayList<>();

    public TestFixtures(UserRepository userRepository,
                        RoleRepository roleRepository,
                        ChatSessionRepository chatSessionRepository,
                        MessageRepository messageRepository,
                        TaskRepository taskRepository,
                        DocumentRepository documentRepository,
                        ActionAuditRepository actionAuditRepository,
                        CitationRepository citationRepository,
                        PasswordEncoder passwordEncoder,
                        JwtService jwtService,
                        @Value("${app.uploads.dir:uploads}") String uploadDir) {
        this.userRepository = userRepository;
        this.roleRepository = roleRepository;
        this.chatSessionRepository = chatSessionRepository;
        this.messageRepository = messageRepository;
        this.taskRepository = taskRepository;
        this.documentRepository = documentRepository;
        this.actionAuditRepository = actionAuditRepository;
        this.citationRepository = citationRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
        this.uploadDir = uploadDir;
    }

    // --- Users ---------------------------------------------------------------

    public User user(RoleName... roleNames) {
        return user("user-" + UUID.randomUUID() + "@test.local", PASSWORD, roleNames);
    }

    public User user(String email, String rawPassword, RoleName... roleNames) {
        User user = new User(email, passwordEncoder.encode(rawPassword), "Test User", Instant.now());

        for (RoleName name : roleNames.length == 0 ? new RoleName[]{RoleName.ROLE_USER} : roleNames) {
            Role role = roleRepository.findByName(name)
                    .orElseThrow(() -> new IllegalStateException(name + " missing; V10 seeds it"));
            user.addRole(role);
        }

        User saved = userRepository.saveAndFlush(user);
        createdUserIds.add(saved.getId());
        return saved;
    }

    /**
     * Deletes everything created since the last call. For non-transactional tests,
     * from an @AfterEach.
     *
     * <p>Deleting the users is enough: sessions, messages, tasks, documents, audit
     * rows, refresh tokens and reset tokens all cascade from them.
     */
    public void cleanUp() {
        for (UUID id : createdUserIds) {
            userRepository.deleteById(id);
        }
        userRepository.flush();
        createdUserIds.clear();
    }

    // --- Owned data ----------------------------------------------------------

    public ChatSession session(User owner, String title) {
        Instant now = Instant.now();
        return chatSessionRepository.saveAndFlush(
                new ChatSession(owner, title, now, now, "preview of " + title));
    }

    public Message message(ChatSession session, String content, MessageSender sender) {
        return messageRepository.saveAndFlush(
                new Message(session.getId(), content, sender, Instant.now()));
    }

    public Task task(ChatSession session, String title) {
        return taskRepository.saveAndFlush(
                new Task(title, TaskPriority.medium, TaskStatus.todo, Instant.now(), session.getId()));
    }

    /**
     * Creates a {@code document_chunks} row — with raw SQL, necessarily.
     *
     * <p>{@link com.knowledgeassistant.document.DocumentChunk} maps only what a
     * citation needs, and {@code embedding vector(384)} is both NOT NULL and deliberately
     * unmapped: Hibernate has no pgvector type, and Java has no use for 384 floats it would
     * immediately discard. So the entity can be READ but not written through JPA, which is
     * exactly right — in production Python writes these rows and Spring only reads them.
     *
     * <p>The vector is zeros. Nothing in this test path searches it; writing a realistic
     * unit-norm vector here would imply a similarity guarantee the fixture cannot make.
     */
    public UUID documentChunk(Document document, int ordinal, String text, String section) {
        UUID id = UUID.randomUUID();
        String zeroVector = "[" + "0,".repeat(383) + "0]";

        entityManager.createNativeQuery("""
                INSERT INTO document_chunks
                    (id, document_id, ordinal, text, token_count, char_start, char_end,
                     section, embedding, embedding_model, embedding_model_revision)
                VALUES (:id, :documentId, :ordinal, :text, 1, 0, 1,
                        :section, CAST(:embedding AS vector), 'fixture', 'fixture')
                """)
                .setParameter("id", id)
                .setParameter("documentId", document.getId())
                .setParameter("ordinal", ordinal)
                .setParameter("text", text)
                .setParameter("section", section)
                .setParameter("embedding", zeroVector)
                .executeUpdate();

        return id;
    }

    /**
     * Tasks belonging to this user's sessions.
     *
     * <p>Exists for one assertion: that PROPOSING an action writes nothing. The whole
     * boundary rests on it — the assistant suggests, a human decides, and only an approval
     * through the governance flow creates a row.
     */
    public long taskCount(User owner) {
        List<UUID> sessionIds = chatSessionRepository.findAll().stream()
                .filter(s -> s.getUser() != null && owner.getId().equals(s.getUser().getId()))
                .map(ChatSession::getId)
                .toList();
        return taskRepository.findAll().stream()
                .filter(t -> sessionIds.contains(t.getSessionId()))
                .count();
    }

    public Document document(User owner, String filename) {
        return document(owner, filename, DocumentStatus.ready);
    }

    /**
     * Creates a document AND the bytes behind it.
     *
     * <p>Writing the file matters: a row with a storage_path pointing at nothing is not
     * a document, and the download endpoint correctly refuses to serve it. A fixture
     * that skipped this would make a real 404 look like a broken test.
     */
    public Document document(User owner, String filename, DocumentStatus status) {
        Document document = new Document(
                owner, filename, 1024L, Instant.now(), status, "text/plain");
        documentRepository.saveAndFlush(document);

        try {
            Path root = Paths.get(uploadDir).toAbsolutePath().normalize();
            Files.createDirectories(root);
            Files.write(root.resolve(document.getId().toString()),
                    ("Fixture content for " + filename).getBytes(StandardCharsets.UTF_8));
        } catch (IOException e) {
            throw new UncheckedIOException("Could not write fixture file for " + filename, e);
        }

        document.setStoragePath(uploadDir + "/" + document.getId());
        return documentRepository.saveAndFlush(document);
    }

    /**
     * Links a message to a document, which is what makes the document undeletable.
     *
     * <p>`citations.document_id` is ON DELETE RESTRICT, so this is the fixture that creates
     * the condition the deletion-impact endpoint exists to report on. Without a citation a
     * document deletes without ceremony.
     */
    public Citation citation(Message message, Document document) {
        return citationRepository.saveAndFlush(new Citation(
                message.getId(), document, "Section 1",
                "An excerpt from " + document.getFilename(), Instant.now()));
    }

    public ActionAudit audit(ChatSession session, String actionId) {
        return actionAuditRepository.saveAndFlush(new ActionAudit(
                actionId, session.getId(), ActionType.CREATE_TASK, ActionDecision.approved, Instant.now()));
    }

    // --- Authentication -------------------------------------------------------

    /**
     * A real signed access token, so requests still traverse the whole
     * JwtAuthenticationFilter path — signature, issuer, expiry, claim mapping.
     */
    public String tokenFor(User user) {
        return jwtService.generateAccessToken(UserPrincipal.from(user));
    }

    public RequestPostProcessor as(User user) {
        return bearer(tokenFor(user));
    }

    public RequestPostProcessor bearer(String token) {
        return request -> {
            request.addHeader("Authorization", "Bearer " + token);
            return request;
        };
    }
}
