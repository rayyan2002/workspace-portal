package com.knowledgeassistant.genai;

import com.knowledgeassistant.genai.dto.GenAiAnswerRequest;
import com.knowledgeassistant.genai.dto.GenAiAnswerResponse;
import com.knowledgeassistant.genai.dto.GenAiCitation;
import com.knowledgeassistant.genai.dto.GenAiTurn;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Spring's client, checked against the spec the GenAI service publishes.
 *
 * <p>This closes BACKLOG.md item 3a. The Python side generates {@code /openapi.json} from
 * the same Pydantic models that validate its requests, so that side cannot drift from
 * itself. <strong>This side can</strong>, and until now nothing compared the two: the DTOs
 * were hand-written and the only safety net was a 422 at runtime, in production, on the
 * first request after someone renamed a field.
 *
 * <p>The spec is committed as {@code src/test/resources/genai-openapi.json}, captured by a
 * command (see benchmarks/COMMANDS.md). Deriving the assertions FROM that file rather than
 * restating them by hand is the point — a hand-written list of expected fields is a sixth
 * copy of the contract, and sixth copies are what this whole project keeps finding broken.
 *
 * <p><strong>Why a conformance test rather than generated model classes.</strong> Generating
 * Java records from the spec gives a compile error on drift, which is stronger. It also
 * replaces DTOs whose comments carry the measured reasoning behind each field — why
 * {@code allowed_document_ids} has no default, why {@code Citation} has no ordinal, why
 * responses tolerate unknown fields while requests forbid them. Those comments are the most
 * valuable thing in the package. This test gives the same drift detection at build time and
 * keeps them; swapping to codegen later is a contained change.
 */
class GenAiSpecConformanceTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static JsonNode schemas;

    @BeforeAll
    static void loadSpec() throws Exception {
        try (InputStream in = GenAiSpecConformanceTest.class
                .getResourceAsStream("/genai-openapi.json")) {
            assertNotNull(in, "genai-openapi.json is missing — capture it, see COMMANDS.md");
            schemas = MAPPER.readTree(in).path("components").path("schemas");
        }
    }

    /** The wire names a record actually serialises, taken from @JsonProperty. */
    private static Set<String> wireNamesOf(Class<?> record) {
        return Arrays.stream(record.getRecordComponents())
                .map(GenAiSpecConformanceTest::wireName)
                .collect(Collectors.toCollection(LinkedHashSet::new));
    }

    /**
     * The name Jackson will actually put on the wire.
     *
     * <p>Read from the backing FIELD, not the record component. {@code @JsonProperty} does
     * not declare {@code RECORD_COMPONENT} among its targets, so it is propagated to the
     * field, accessor and constructor parameter and is invisible to
     * {@code RecordComponent.getAnnotation}. Asking the component returns the Java name —
     * which is exactly the camelCase this test exists to catch, so the test would have
     * failed loudly against correct code.
     */
    private static String wireName(RecordComponent component) {
        try {
            JsonProperty annotation = component.getDeclaringRecord()
                    .getDeclaredField(component.getName())
                    .getAnnotation(JsonProperty.class);
            return annotation != null ? annotation.value() : component.getName();
        } catch (NoSuchFieldException impossible) {
            throw new AssertionError("a record component with no backing field", impossible);
        }
    }

    private static Set<String> specPropertiesOf(String schemaName) {
        JsonNode properties = schemas.path(schemaName).path("properties");
        assertTrue(properties.isObject(), "no schema named " + schemaName + " in the spec");
        Set<String> names = new LinkedHashSet<>();
        properties.fieldNames().forEachRemaining(names::add);
        return names;
    }

    @Test
    void everyFieldSpringSendsExistsInTheSpec() {
        // RetrievalRequest sets extra="forbid", so ONE field this service does not know
        // about is a 422 on every request — not a warning, not a dropped value.
        Set<String> sent = wireNamesOf(GenAiAnswerRequest.class);
        Set<String> accepted = specPropertiesOf("RetrievalRequest");

        Set<String> unknown = new LinkedHashSet<>(sent);
        unknown.removeAll(accepted);

        assertTrue(unknown.isEmpty(),
                "Spring sends fields the service would reject with 422: " + unknown);
    }

    @Test
    void everyFieldTheSpecRequiresIsSentBySpring() {
        // Omission is a 422 too, and is the louder half: `allowed_document_ids` has no
        // default precisely so a Spring bug cannot silently become an unfiltered search.
        JsonNode required = schemas.path("RetrievalRequest").path("required");
        Set<String> sent = wireNamesOf(GenAiAnswerRequest.class);

        required.forEach(field ->
                assertTrue(sent.contains(field.asText()),
                        "the spec requires '" + field.asText() + "' and Spring does not send it"));
    }

    @Test
    void springUsesTheSpecsNamesExactly() {
        // camelCase is the drift that costs a whole afternoon: every request 422s and the
        // symptom reads as "the AI is broken" rather than "a field was renamed".
        // include_raw is NOT here: it is a diagnostic the service defaults to false and
        // Spring deliberately never sets. benchmarks/19 is its only caller.
        assertEquals(Set.of("question", "allowed_document_ids", "top_k", "min_score",
                        "session_id", "history", "model"),
                wireNamesOf(GenAiAnswerRequest.class));
        assertTrue(specPropertiesOf("RetrievalRequest")
                .containsAll(wireNamesOf(GenAiAnswerRequest.class)));
    }

    @Test
    void everyFieldSpringReadsFromAResponseStillExists() {
        // The asymmetry: responses tolerate UNKNOWN fields, which is what let Python add
        // four trace fields across Days 6-12 without breaking this client. What it must not
        // do is REMOVE one Spring reads — @JsonIgnoreProperties makes that silently null.
        assertTrue(specPropertiesOf("AnswerResponse").containsAll(
                wireNamesOf(GenAiAnswerResponse.class)),
                "AnswerResponse lost a field Spring reads");

        assertTrue(specPropertiesOf("Citation").containsAll(wireNamesOf(GenAiCitation.class)),
                "Citation lost a field Spring reads");

        assertTrue(specPropertiesOf("ConversationTurn").containsAll(wireNamesOf(GenAiTurn.class)),
                "ConversationTurn lost a field Spring sends");
    }

    @Test
    void theSpecStillDescribesTheEndpointSpringCalls() {
        assertTrue(schemas.path("RetrievalRequest").isObject(), "the /answer request shape is gone");
        assertTrue(schemas.path("AnswerResponse").isObject(), "the /answer response shape is gone");
    }

    @Test
    void theCommittedSpecIsNotAStaleFragment() {
        // A snapshot that silently emptied would make every assertion above vacuous.
        assertTrue(schemas.size() >= 20, "the committed spec looks truncated: " + schemas.size());
    }
}
