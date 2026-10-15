package com.knowledgeassistant.performance;

import com.knowledgeassistant.common.PageRequestFactory;
import com.knowledgeassistant.support.TestFixtures;
import com.knowledgeassistant.user.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * The page envelope, and the clamp that stops a client asking for the whole table.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class PaginationTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private TestFixtures fixtures;

    private User owner;

    @BeforeEach
    void setUp() {
        owner = fixtures.user();
        for (int i = 0; i < 25; i++) {
            fixtures.document(owner, "doc-" + i + ".txt");
        }
    }

    @Test
    void listsReturnTheAgreedEnvelope() throws Exception {
        mockMvc.perform(get("/api/documents").with(fixtures.as(owner)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isArray())
                .andExpect(jsonPath("$.total").value(25))
                .andExpect(jsonPath("$.page").value(0))
                .andExpect(jsonPath("$.size").value(PageRequestFactory.DEFAULT_SIZE))
                .andExpect(jsonPath("$.items.length()").value(PageRequestFactory.DEFAULT_SIZE));
    }

    @Test
    void totalCountsEveryMatchingRowNotJustThePage() throws Exception {
        // The whole reason the envelope exists: 20 items but 25 total, so a pager can
        // tell the user there is more.
        mockMvc.perform(get("/api/documents?page=1&size=20").with(fixtures.as(owner)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(5))
                .andExpect(jsonPath("$.total").value(25))
                .andExpect(jsonPath("$.page").value(1));
    }

    @Test
    void anAbsurdPageSizeIsClampedRatherThanHonoured() throws Exception {
        // ?size=1000000 is a one-request denial of service: load the table into
        // memory, serialise it, hold a connection throughout. Page size is proposed
        // by the client and decided by the server.
        mockMvc.perform(get("/api/documents?size=1000000").with(fixtures.as(owner)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.size").value(PageRequestFactory.MAX_SIZE));
    }

    @Test
    void negativeAndNonsensicalParametersFallBackToDefaults() throws Exception {
        mockMvc.perform(get("/api/documents?page=-5&size=-1").with(fixtures.as(owner)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(0))
                .andExpect(jsonPath("$.size").value(PageRequestFactory.DEFAULT_SIZE));
    }

    @Test
    void searchIsAppliedInTheDatabaseAcrossEveryPage() throws Exception {
        fixtures.document(owner, "quarterly-report.pdf");

        // Would fail if filtering were client-side: the match is on page 2 of the
        // unfiltered list, so a page-local filter would never see it.
        mockMvc.perform(get("/api/documents?search=quarterly").with(fixtures.as(owner)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].filename").value("quarterly-report.pdf"));
    }

    @Test
    void anAbsentSearchTermDoesNotBreakTheQuery() throws Exception {
        // Regression: a null String parameter has no JDBC type, so the driver sent it
        // as bytea and Postgres rejected LOWER(bytea). Every unfiltered document list
        // was a 500.
        mockMvc.perform(get("/api/documents").with(fixtures.as(owner)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(25));
    }
}
