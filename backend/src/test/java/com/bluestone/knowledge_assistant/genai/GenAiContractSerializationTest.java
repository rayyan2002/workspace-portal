package com.bluestone.knowledge_assistant.genai;

import com.bluestone.knowledge_assistant.genai.dto.GenAiAnswerRequest;
import com.bluestone.knowledge_assistant.genai.dto.GenAiAnswerResponse;
import com.bluestone.knowledge_assistant.genai.dto.GenAiTurn;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The wire format, asserted rather than assumed.
 *
 * <p>BACKLOG.md 3a: Spring's GenAI client is hand-written against the FastAPI spec and
 * nothing compares them. The Python side generates its OpenAPI document from the same
 * Pydantic models that validate its requests, so it cannot drift from itself. This side can.
 *
 * <p>These tests are not the fix — generating the client from {@code /openapi.json}, or
 * asserting against the live spec, is the fix. They are the cheap half: every Pydantic model
 * on that boundary sets {@code extra="forbid"}, so one camelCase field name is a 422 on every
 * request, and the failure would otherwise surface as "the AI is broken" rather than "a field
 * was renamed". They run without Python, which is the point — a Spring test must not need
 * another runtime to be up.
 */
class GenAiContractSerializationTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void requestUsesExactlyTheFieldNamesPythonAccepts() throws Exception {
        GenAiAnswerRequest request = new GenAiAnswerRequest(
                "What is the leave policy?",
                List.of(UUID.fromString("11111111-1111-1111-1111-111111111111")),
                5, 0.60,
                UUID.fromString("22222222-2222-2222-2222-222222222222"),
                List.of(new GenAiTurn("user", "what are the formulas of adbms")), null);

        JsonNode json = mapper.readTree(mapper.writeValueAsString(request));

        // snake_case, exactly. RetrievalRequest forbids anything else.
        assertTrue(json.has("allowed_document_ids"), "must be snake_case: allowed_document_ids");
        assertTrue(json.has("top_k"), "must be snake_case: top_k");
        assertTrue(json.has("min_score"), "must be snake_case: min_score");
        assertTrue(json.has("session_id"), "must be snake_case: session_id");
        assertTrue(json.has("question"));
        assertTrue(json.has("history"), "must be snake_case: history");

        // And nothing else. An extra field is a 422, not a warning.
        assertEquals(6, json.size(), "an unexpected field would be rejected by extra=forbid");
        assertFalse(json.has("allowedDocumentIds"), "camelCase would be a 422 on every request");
    }

    @Test
    void anEmptyAllowListIsSerialisedAsAnEmptyList_neverOmitted() throws Exception {
        GenAiAnswerRequest request = new GenAiAnswerRequest("q", List.of(), 5, 0.60, null, List.of(), null);

        JsonNode json = mapper.readTree(mapper.writeValueAsString(request));

        // Omitting the field is a 422 by design — Spring always knows the answer, so
        // omission would be a bug here and the contract makes it loud. Empty, by contrast,
        // is a NORMAL state: a user with no ready documents.
        assertTrue(json.has("allowed_document_ids"));
        assertTrue(json.get("allowed_document_ids").isArray());
        assertEquals(0, json.get("allowed_document_ids").size());
    }

    @Test
    void responseToleratesTraceFieldsThisClientDoesNotKnow() throws Exception {
        // The asymmetry that makes the boundary safe to extend: requests forbid unknown
        // fields so Spring sending garbage is loud, responses tolerate them so Python can add
        // a trace field without breaking this client on deploy. It added two in two days —
        // collapsed_duplicates on Day 6, dropped_quotes on Day 7.
        String body = """
                {"outcome":"grounded","answer":"Twenty days.",
                 "citations":[{"chunk_id":"11111111-1111-1111-1111-111111111111",
                               "document_id":"22222222-2222-2222-2222-222222222222","score":0.81}],
                 "proposals":[],
                 "trace":{"trace_id":"abc","collapsed_duplicates":3,"dropped_quotes":[],
                          "a_field_invented_next_tuesday":true}}
                """;

        GenAiAnswerResponse response = mapper.readValue(body, GenAiAnswerResponse.class);

        assertEquals("grounded", response.outcome());
        assertFalse(response.isInsufficientContext());
        assertEquals(1, response.citations().size());
        assertEquals(3, response.trace().collapsedDuplicates());
    }

    @Test
    void insufficientContextIsRecognisedByItsExactSpelling() throws Exception {
        String body = """
                {"outcome":"insufficient_context","answer":"","citations":[],"proposals":[],"trace":null}
                """;

        GenAiAnswerResponse response = mapper.readValue(body, GenAiAnswerResponse.class);

        assertTrue(response.isInsufficientContext());
        assertTrue(response.answer().isEmpty());
    }
}
