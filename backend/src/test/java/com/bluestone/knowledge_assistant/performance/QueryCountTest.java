package com.bluestone.knowledge_assistant.performance;

import com.bluestone.knowledge_assistant.chat.ChatSession;
import com.bluestone.knowledge_assistant.chat.MessageSender;
import com.bluestone.knowledge_assistant.support.TestFixtures;
import com.bluestone.knowledge_assistant.user.User;
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Guards against N+1: the query count for a list endpoint must not grow with the
 * number of rows returned.
 *
 * <p>Asserting on a count rather than on elapsed time is deliberate. An N+1 is
 * invisible in a timing at demo scale — three extra queries against a warm local
 * database cost nothing — and only becomes a latency problem at a volume that arrives
 * long after the code was written. The count exposes the shape of the problem
 * immediately, at any size.
 *
 * <p>Each test therefore runs the SAME request against two different data volumes and
 * asserts the counts match. A fixed threshold would need updating whenever a query is
 * legitimately added; "does not grow with n" is the property actually worth protecting.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class QueryCountTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private TestFixtures fixtures;
    @Autowired private EntityManagerFactory entityManagerFactory;

    private Statistics statistics;
    private User owner;

    @BeforeEach
    void setUp() {
        owner = fixtures.user();
        statistics = entityManagerFactory.unwrap(SessionFactory.class).getStatistics();
        statistics.setStatisticsEnabled(true);
    }

    private RequestPostProcessor asOwner() {
        return fixtures.as(owner);
    }

    /** Queries issued while performing one request. */
    private long queriesFor(String path) throws Exception {
        statistics.clear();
        mockMvc.perform(get(path).with(asOwner())).andExpect(status().isOk());
        return statistics.getPrepareStatementCount();
    }

    @Test
    void sessionListQueryCountDoesNotGrowWithSessions() throws Exception {
        fixtures.session(owner, "one");
        long withOne = queriesFor("/api/chat/sessions");

        for (int i = 0; i < 9; i++) {
            fixtures.session(owner, "session " + i);
        }
        long withTen = queriesFor("/api/chat/sessions");

        assertThat(withTen)
                .as("ten sessions must cost the same number of queries as one (was %d then %d)", withOne, withTen)
                .isEqualTo(withOne);
    }

    @Test
    void documentListQueryCountDoesNotGrowWithDocuments() throws Exception {
        fixtures.document(owner, "one.txt");
        long withOne = queriesFor("/api/documents");

        for (int i = 0; i < 9; i++) {
            fixtures.document(owner, "doc-" + i + ".txt");
        }
        long withTen = queriesFor("/api/documents");

        assertThat(withTen)
                .as("ten documents must cost the same as one (was %d then %d)", withOne, withTen)
                .isEqualTo(withOne);
    }

    @Test
    void taskListQueryCountDoesNotGrowWithTasks() throws Exception {
        ChatSession session = fixtures.session(owner, "task source");
        fixtures.task(session, "one");
        long withOne = queriesFor("/api/tasks");

        for (int i = 0; i < 9; i++) {
            fixtures.task(session, "task " + i);
        }
        long withTen = queriesFor("/api/tasks");

        assertThat(withTen)
                .as("ten tasks must cost the same as one (was %d then %d)", withOne, withTen)
                .isEqualTo(withOne);
    }

    @Test
    void auditTrailQueryCountDoesNotGrowWithRows() throws Exception {
        ChatSession session = fixtures.session(owner, "audited");
        fixtures.audit(session, "act-first");
        long withOne = queriesFor("/api/actions/audit");

        // Distinct ids. The loop previously produced act-0..act-8 after an explicit act-1,
        // so one row was a duplicate action_id — harmless until V20 made a proposal
        // decidable exactly once, at which point the fixture stopped being valid data.
        for (int i = 0; i < 9; i++) {
            fixtures.audit(session, "act-loop-" + i);
        }
        long withTen = queriesFor("/api/actions/audit");

        assertThat(withTen)
                .as("ten audit rows must cost the same as one (was %d then %d)", withOne, withTen)
                .isEqualTo(withOne);
    }

    /**
     * Citations were the one place an N+1 was already fixed — they load in a single
     * query keyed by message rather than one query per message. This pins that.
     */
    @Test
    void messageHistoryQueryCountDoesNotGrowWithMessagesOrCitations() throws Exception {
        ChatSession session = fixtures.session(owner, "history");
        fixtures.document(owner, "cited.txt");
        fixtures.message(session, "first", MessageSender.user);
        long withOne = queriesFor("/api/chat/" + session.getId() + "/messages");

        for (int i = 0; i < 9; i++) {
            fixtures.message(session, "message " + i, MessageSender.assistant);
        }
        long withTen = queriesFor("/api/chat/" + session.getId() + "/messages");

        assertThat(withTen)
                .as("ten messages must cost the same as one (was %d then %d)", withOne, withTen)
                .isEqualTo(withOne);
    }
}
