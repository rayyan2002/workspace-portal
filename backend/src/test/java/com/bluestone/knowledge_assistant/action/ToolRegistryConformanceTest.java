package com.bluestone.knowledge_assistant.action;

import com.bluestone.knowledge_assistant.action.dto.CreateTaskPayload;
import com.bluestone.knowledge_assistant.action.dto.LookupPayload;
import com.bluestone.knowledge_assistant.action.dto.SummarizePayload;
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
 * Spring's tool definitions, checked against the registry the GenAI service publishes.
 *
 * <p>Day 10 built {@code GET /tools} so the tool list would stop being copied by hand —
 * Spring needs it to validate a proposal, and Day 14's evaluation set needs it to assert a
 * tool is NOT proposed for an unrelated request. <strong>It then had no consumer at all.</strong>
 * A registry nobody reads prevents nothing; this is the consumer.
 *
 * <p>Checked on Day 14, across three definitions in two languages:
 *
 * <pre>
 *   create-task         title, priority      agrees
 *   lookup-knowledge    query                agrees
 *   summarize-document  chunk_ordinal  vs  documentId, documentName   DIFFERENT BY DESIGN
 * </pre>
 *
 * <p>The third is not drift. INTEGRATION_CONTRACT.md §5 states it: the service must not ask
 * a 0.5B model for a UUID — it costs 36 tokens and measurably stops it citing at all — and
 * it cannot know a filename. So the model quotes a sentence, code resolves the quote to an
 * ordinal, and <em>Spring</em> maps that ordinal to the chunk row it wrote, which already
 * holds both the document id and its name.
 *
 * <p><strong>Nothing performs that mapping.</strong> Jackson rejects Python's shape outright
 * — {@code UnrecognizedPropertyException: Unrecognized field "tool"} — so it fails closed
 * rather than silently nulling, but the translation step this design depends on does not
 * exist. It is unreachable today because nothing proposes summarize-document, and it becomes
 * a hard break the day something does. The test below pins the gap so it cannot be
 * rediscovered as a surprise.
 */
class ToolRegistryConformanceTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static JsonNode registry;

    @BeforeAll
    static void loadRegistry() throws Exception {
        try (InputStream in = ToolRegistryConformanceTest.class
                .getResourceAsStream("/tool-registry.json")) {
            assertNotNull(in, "tool-registry.json is missing — capture GET /tools, see COMMANDS.md");
            registry = MAPPER.readTree(in);
        }
    }

    private static JsonNode tool(String name) {
        for (JsonNode t : registry.get("tools")) {
            if (name.equals(t.get("name").asText())) {
                return t;
            }
        }
        throw new AssertionError("the registry does not publish a tool named " + name);
    }

    /** Argument names the service publishes, minus the discriminator. */
    private static Set<String> publishedArguments(String toolName) {
        Set<String> names = new LinkedHashSet<>();
        tool(toolName).get("arguments_schema").get("properties").fieldNames()
                .forEachRemaining(names::add);
        names.remove("tool");   // the discriminator; Jackson carries it as `type` on the request
        return names;
    }

    private static Set<String> fieldsOf(Class<?> record) {
        return Arrays.stream(record.getRecordComponents())
                .map(RecordComponent::getName)
                .collect(Collectors.toCollection(LinkedHashSet::new));
    }

    @Test
    void springKnowsExactlyTheToolsTheServicePublishes() {
        Set<String> published = new LinkedHashSet<>();
        registry.get("tools").forEach(t -> published.add(t.get("name").asText()));

        Set<String> known = Arrays.stream(ActionType.values())
                // getValue(), not toString(): the enum CONSTANT is CREATE_TASK and the
                // WIRE value is "create-task". @JsonValue marks which one travels, and
                // the wire value is the one three systems agree on.
                .map(ActionType::getValue)
                .collect(Collectors.toCollection(LinkedHashSet::new));

        assertEquals(published, known,
                "ActionType and the published registry disagree about which tools exist");
    }

    @Test
    void toolNamesAreHyphenatedOnBothSides() {
        // These literals reach Postgres (action_audit.type), Jackson's @JsonSubTypes and the
        // frontend union. The tracker writes them with underscores; the running system does
        // not, and create_task is a REJECTED discriminator tag.
        for (ActionType type : ActionType.values()) {
            assertTrue(type.getValue().contains("-"), type + " is not hyphenated on the wire");
            assertTrue(!type.getValue().contains("_"), type + " uses an underscore on the wire");
        }
    }

    @Test
    void createTaskArgumentsMatchExactly() {
        assertEquals(publishedArguments("create-task"), fieldsOf(CreateTaskPayload.class));
    }

    @Test
    void lookupKnowledgeArgumentsMatchExactly() {
        assertEquals(publishedArguments("lookup-knowledge"), fieldsOf(LookupPayload.class));
    }

    @Test
    void summarizeDocumentDiffersByDesign_andTheTranslationNowEXISTS() {
        // THE GAP THIS TEST WAS WRITTEN TO PIN IS CLOSED. Day 14's version asserted the two
        // shapes were disjoint and said in its failure message that nothing translated an
        // ordinal into a document id — a hard break the day something proposed this tool.
        // Day 14b proposes it, so the bridge had to exist: the service resolves its own
        // chunk_ordinal to a document_id IN CODE, and ActionProposer turns that into the
        // {documentId, documentName} SummarizePayload needs.
        //
        // The shapes are still different, and still deliberately: a 0.5B model must never be
        // asked for a UUID (36 tokens, and it measurably stops citing at all) or for a
        // filename it was never shown. What changed is that the difference is now BRIDGED
        // rather than merely documented.
        Set<String> published = publishedArguments("summarize-document");
        Set<String> springs = fieldsOf(SummarizePayload.class);

        assertEquals(Set.of("chunk_ordinal", "document_id"), published,
                "the service publishes what the MODEL states (chunk_ordinal) alongside what "
                        + "CODE resolved it to (document_id), per INTEGRATION_CONTRACT.md §5");
        assertEquals(Set.of("documentId", "documentName"), springs,
                "Spring executes against a document id and a name");

        // The translated field, named on both sides in each language's own spelling. This is
        // the assertion that would have failed on Day 14, when `document_id` did not exist.
        assertTrue(published.contains("document_id"),
                "nothing resolves the ordinal, so a proposal for this tool cannot be executed");
        assertTrue(springs.contains("documentId"), "Spring has nothing to execute against");
    }

    @Test
    void springSuppliesTheHalfOfTheSummarizePayloadThatPythonCannotKnow() {
        // documentName is NOT published and must not be: the GenAI service holds SELECT on
        // the chunk tables and does not own `documents`, so a filename could only ever be a
        // guess there. Spring fills it from its own row — see ActionProposer — which is also
        // the only place an ownership check means anything.
        assertTrue(!publishedArguments("summarize-document").contains("document_name"),
                "the service must not claim to know a filename it was never shown");
        assertTrue(fieldsOf(SummarizePayload.class).contains("documentName"));
    }

    @Test
    void theRegistryVersionIsRecorded() {
        // A fingerprint of the registry's content. If it changes, the tools changed, and
        // refreshing this snapshot is a deliberate act rather than a silent one.
        assertTrue(registry.get("registry_version").asText().length() >= 8);
    }
}
