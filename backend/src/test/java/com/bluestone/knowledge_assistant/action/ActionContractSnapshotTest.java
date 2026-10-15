package com.bluestone.knowledge_assistant.action;

import com.bluestone.knowledge_assistant.action.dto.ActionPayload;
import com.bluestone.knowledge_assistant.action.dto.CreateTaskPayload;
import com.bluestone.knowledge_assistant.action.dto.LookupPayload;
import com.bluestone.knowledge_assistant.action.dto.LookupResult;
import com.bluestone.knowledge_assistant.action.dto.SummarizePayload;
import com.bluestone.knowledge_assistant.action.dto.SummarizeResult;
import com.bluestone.knowledge_assistant.task.TaskPriority;
import com.bluestone.knowledge_assistant.task.TaskStatus;
import com.bluestone.knowledge_assistant.task.dto.TaskDto;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.lang.reflect.Field;
import java.lang.reflect.RecordComponent;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Day 14b: Spring's half of the browser contract, asserted against a committed snapshot.
 *
 * <p><strong>This test exists so the FRONTEND can be tested at all.</strong> The GenAI
 * boundary has had conformance tests since Day 14 — one against {@code /openapi.json}, one
 * against {@code GET /tools} — so Java and Python cannot drift without a build failing. The
 * browser boundary had none: {@code Type.ts} was hand-written against these very records and
 * checked by nobody, which is two of the four hand-maintained copies that caused the Month 2
 * drift in the first place.
 *
 * <p>The snapshot at {@code src/test/resources/action-contract.json} is the shared artefact.
 * This test holds SPRING to it by reflection; an identical copy sits at
 * {@code src/test/action-contract.json} in the frontend repo, where a vitest test holds
 * {@code Type.ts} to it. Neither side can edit it to make itself pass — changing it to suit
 * the frontend fails this test, and changing these records fails this test until the
 * snapshot is regenerated, at which point the frontend fails until {@code Type.ts} follows.
 *
 * <p>It found two real defects before it had guarded anything, which is recorded in the
 * snapshot's own {@code _about} and in Day 14b's notes.
 *
 * <p><strong>Field names are read from the backing FIELD, not the RecordComponent.</strong>
 * {@code @JsonProperty} on a record component is propagated to the field, and
 * {@code RecordComponent.getAnnotation} does not see it — a trap this suite already walked
 * into once on {@code GenAiSpecConformanceTest}, where a correct DTO failed a wrong test.
 * {@code TaskDto.sessionId} is exactly that case: it serialises as {@code sourceSessionId}.
 */
class ActionContractSnapshotTest {

    private static JsonNode contract;

    @BeforeAll
    static void load() throws Exception {
        try (InputStream in = ActionContractSnapshotTest.class
                .getResourceAsStream("/action-contract.json")) {
            assertNotNull(in, "action-contract.json is missing from the test resources");
            contract = new ObjectMapper().readTree(in);
        }
    }

    private static List<String> strings(JsonNode node) {
        List<String> out = new ArrayList<>();
        node.forEach(n -> out.add(n.asText()));
        return out;
    }

    /** The JSON names a record serialises to, in declaration order. */
    private static Set<String> wireFieldsOf(Class<?> record) {
        Set<String> names = new LinkedHashSet<>();
        for (RecordComponent component : record.getRecordComponents()) {
            JsonProperty annotation = null;
            try {
                Field backing = record.getDeclaredField(component.getName());
                annotation = backing.getAnnotation(JsonProperty.class);
            } catch (NoSuchFieldException impossible) {
                // A record always has a backing field for each component.
            }
            names.add(annotation != null && !annotation.value().isBlank()
                    ? annotation.value()
                    : component.getName());
        }
        return names;
    }

    // --- the vocabularies -----------------------------------------------------

    @Test
    void actionTypesMatchTheSnapshot() {
        assertEquals(strings(contract.get("actionTypes")),
                java.util.Arrays.stream(ActionType.values()).map(ActionType::getValue).toList(),
                "ActionType and the published action contract disagree");
    }

    @Test
    void decisionsMatchTheSnapshot() {
        assertEquals(strings(contract.get("decisions")),
                java.util.Arrays.stream(ActionDecision.values()).map(Enum::name).toList());
    }

    @Test
    void statusesMatchTheSnapshot() {
        // The one the frontend got wrong. Type.ts exported
        // ActionStatus = 'pending' | 'approved' | 'rejected', which is neither this enum nor
        // ActionDecision — it had no consumers, which is the only reason nothing broke.
        assertEquals(strings(contract.get("statuses")),
                java.util.Arrays.stream(ActionStatus.values()).map(Enum::name).toList());
    }

    @Test
    void prioritiesAndTaskStatusesMatchTheSnapshot() {
        assertEquals(strings(contract.get("priorities")),
                java.util.Arrays.stream(TaskPriority.values()).map(Enum::name).toList());
        assertEquals(strings(contract.get("taskStatuses")),
                java.util.Arrays.stream(TaskStatus.values()).map(TaskStatus::getValue).toList(),
                "TaskStatus serialises via @JsonValue, so in_progress reaches the browser "
                        + "as in-progress");
    }

    // --- payloads, which the browser SENDS ------------------------------------

    @Test
    void everyPayloadShapeMatchesTheSnapshot() {
        JsonNode payloads = contract.get("payloads");
        assertEquals(new LinkedHashSet<>(strings(payloads.get("create-task"))),
                wireFieldsOf(CreateTaskPayload.class));
        assertEquals(new LinkedHashSet<>(strings(payloads.get("summarize-document"))),
                wireFieldsOf(SummarizePayload.class));
        assertEquals(new LinkedHashSet<>(strings(payloads.get("lookup-knowledge"))),
                wireFieldsOf(LookupPayload.class));
    }

    @Test
    void everyPermittedPayloadIsCoveredBySnapshot() {
        // ActionPayload is a SEALED interface, so this enumerates the real set rather than a
        // list someone maintains. A fourth payload added without a snapshot entry fails here
        // instead of reaching the browser undocumented — which is how summarize-document
        // went five days without the translation it was specified to have.
        Set<String> documented = new LinkedHashSet<>();
        contract.get("payloads").fieldNames().forEachRemaining(documented::add);

        assertEquals(ActionPayload.class.getPermittedSubclasses().length, documented.size(),
                "ActionPayload permits " + ActionPayload.class.getPermittedSubclasses().length
                        + " payloads and the contract documents " + documented.size());
        assertEquals(documented, new LinkedHashSet<>(strings(contract.get("actionTypes"))),
                "every action type must have exactly one documented payload");
    }

    // --- results, which the browser RECEIVES ----------------------------------

    @Test
    void everyResultShapeMatchesTheSnapshot() {
        JsonNode results = contract.get("results");
        assertEquals(new LinkedHashSet<>(strings(results.get("create-task"))),
                wireFieldsOf(TaskDto.class),
                "an approved create-task returns a TaskDto");
        assertEquals(new LinkedHashSet<>(strings(results.get("summarize-document"))),
                wireFieldsOf(SummarizeResult.class));
        assertEquals(new LinkedHashSet<>(strings(results.get("lookup-knowledge"))),
                wireFieldsOf(LookupResult.class));
    }

    @Test
    void theSummaryIsWrappedRatherThanBare() {
        // THE DEFECT THIS WHOLE SNAPSHOT WAS BUILT CHASING. ActionService returned the
        // summary as a bare String while ActionCard.tsx renders `result.summary`; against a
        // bare string that expression is `undefined`, so an approved summary rendered as an
        // empty card with no error anywhere. A record with one field is not ceremony here —
        // it is the difference between the feature working and silently not.
        assertEquals(Set.of("summary"), wireFieldsOf(SummarizeResult.class));
        assertTrue(SummarizeResult.class.isRecord(),
                "a bare String would deserialise in the browser as a value, not an object");
    }
}
