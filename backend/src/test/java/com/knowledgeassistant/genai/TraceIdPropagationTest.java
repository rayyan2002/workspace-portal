package com.knowledgeassistant.genai;

import com.knowledgeassistant.genai.dto.GenAiAnswerResponse;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.headerDoesNotExist;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

/**
 * Day 18: one trace id spans both services.
 *
 * <p><strong>This was broken for two months while saying so out loud.</strong> The GenAI
 * service logged, on every single request:
 *
 * <pre>  app.trace — no X-Trace-Id header on /answer — caller should propagate it</pre>
 *
 * and {@code trace.py}'s own docstring states "If the header is missing, that is a Spring
 * defect." It was. {@code TraceIdFilter} has stamped every Spring log line with a traceId
 * since Month 2 and returned it to the browser; this client never forwarded it. Every
 * question produced TWO unrelated ids, and no single grep could follow one request from the
 * browser through retrieval and generation — which is exactly what "diagnose a poor AI
 * answer" requires.
 *
 * <p>The warning was correct and visible the whole time, in a log nobody read for that
 * purpose. Same shape as Day 17's finding, and the reason this day exists.
 *
 * <p><strong>These tests drive the REAL client.</strong> The first version could not reach it
 * — {@code GenAiClient} built its {@code RestClient} internally — so it rebuilt the
 * interceptor inside the test and asserted against its own copy. That version would have
 * passed with the production interceptor deleted. The package-private constructor exists so
 * this one cannot.
 */
class TraceIdPropagationTest {

    private static final String ANSWER_BODY = """
            {"outcome":"grounded","answer":"An answer.","citations":[],"proposals":[],"trace":null}""";

    private static final GenAiProperties PROPERTIES = new GenAiProperties(
            "http://localhost:8000", Duration.ofSeconds(150), Duration.ofSeconds(2), 5, 6, 0.60);

    private RestClient.Builder builder;
    private MockRestServiceServer server;

    /** The real client, with a mock server watching the wire underneath it. */
    private GenAiClient client() {
        builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        return new GenAiClient(PROPERTIES, builder);
    }

    @AfterEach
    void clearMdc() {
        // MDC is thread-local and JUnit reuses threads. A leaked traceId would make the next
        // test pass for the wrong reason — the same leak TraceIdFilter's finally-block
        // exists to prevent in production.
        MDC.clear();
    }

    @Test
    void theTraceIdFromMdcReachesTheWire() {
        GenAiClient client = client();
        String traceId = UUID.randomUUID().toString();
        MDC.put("traceId", traceId);

        server.expect(requestTo("http://localhost:8000/answer"))
                .andExpect(header("X-Trace-Id", traceId))
                .andRespond(withSuccess(ANSWER_BODY, MediaType.APPLICATION_JSON));

        GenAiAnswerResponse response = client.answer("q", List.of(), null, List.of(), null);

        assertNotNull(response);
        server.verify();
    }

    @Test
    void noTraceIdInScopeSendsNoHeaderAtAll() {
        // An empty or literal "null" header would be worse than none: the GenAI service would
        // accept it as a real id, stop warning, and correlate every untraced request
        // together under one meaningless value.
        GenAiClient client = client();
        MDC.clear();

        server.expect(requestTo("http://localhost:8000/answer"))
                .andExpect(headerDoesNotExist("X-Trace-Id"))
                .andRespond(withSuccess(ANSWER_BODY, MediaType.APPLICATION_JSON));

        client.answer("q", List.of(), null, List.of(), null);

        server.verify();
    }

    @Test
    void eachRequestCarriesItsOwnCurrentTraceId() {
        // The interceptor must read MDC at REQUEST time, not at construction time. Capturing
        // it in the constructor would stamp every request for the lifetime of the
        // application with whichever id happened to be in scope at startup — which is none.
        GenAiClient client = client();

        MDC.put("traceId", "first-request");
        server.expect(requestTo("http://localhost:8000/answer"))
                .andExpect(header("X-Trace-Id", "first-request"))
                .andRespond(withSuccess(ANSWER_BODY, MediaType.APPLICATION_JSON));
        client.answer("q", List.of(), null, List.of(), null);
        server.verify();

        server.reset();
        MDC.put("traceId", "second-request");
        server.expect(requestTo("http://localhost:8000/answer"))
                .andExpect(header("X-Trace-Id", "second-request"))
                .andRespond(withSuccess(ANSWER_BODY, MediaType.APPLICATION_JSON));
        client.answer("q", List.of(), null, List.of(), null);
        server.verify();
    }

    @Test
    void theHeaderNameIsTheOneTheGenAiServiceActuallyReads() {
        // trace.py declares TRACE_HEADER = "X-Trace-Id". A rename on either side silently
        // restores the original defect: the service would warn again and nobody would
        // notice, because warning is what it did for two months.
        GenAiClient client = client();
        MDC.put("traceId", "abc");

        server.expect(requestTo("http://localhost:8000/answer"))
                .andExpect(request -> assertTrue(
                        request.getHeaders().getFirst("X-Trace-Id") != null,
                        "the header must be spelled exactly as trace.py's TRACE_HEADER, "
                                + "and was not present under that name"))
                .andRespond(withSuccess(ANSWER_BODY, MediaType.APPLICATION_JSON));

        client.answer("q", List.of(), null, List.of(), null);

        server.verify();
    }
}
