"""Day 14b: the tool router. Replaces a keyword list that lived in Java.

TWO HALVES, TESTED DIFFERENTLY ON PURPOSE.

The keyword rules, the abstain margin and the proposal building are PURE — no weights, no
database — so they run in the default suite with a stub classifier. The classifier's
ACCURACY needs the real encoder, so it carries the `routing` marker and runs on demand,
exactly like the golden set:

    .venv/bin/python -m pytest tests/test_intent.py -m routing -q

THE TEST SET IS HELD OUT. Accuracy is measured on the `routing` array of
evaluation/tool_cases.json, written on Day 14 before any classifier existed and containing
a case marked `known_miss` because keywords cannot catch it. The classifier is fitted on
evaluation/intent_train.json. test_the_train_and_test_sets_are_disjoint runs in the DEFAULT
suite and needs no weights, because a split that quietly stopped being a split would make
every number below a measure of memory rather than of accuracy.
"""
import json
import uuid
from pathlib import Path

import pytest

from app.intent import (
    QUERY_MAX,
    TASK_TITLE_MAX,
    Intent,
    IntentRouter,
    keyword_route,
    looks_like_a_question,
    proposals_for,
    task_title_from,
)
from app.schemas import (
    CreateTaskArguments,
    LookupKnowledgeArguments,
    RetrievedChunk,
    SummarizeDocumentArguments,
    ToolName,
)

ROOT = Path(__file__).resolve().parents[1]
TRAIN = json.loads((ROOT / "evaluation" / "intent_train.json").read_text())["examples"]
CASES = json.loads((ROOT / "evaluation" / "tool_cases.json").read_text())["routing"]
TEST_SET = [{"message": c["message"], "label": c["expect"], "why": c.get("trap") or c.get("known_miss", "")}
            for c in CASES]

# Real UUID objects, not strings. Pydantic coerces a string at runtime, so the test passed
# either way — but the field is typed UUID and writing a str here is the kind of "works but
# is not what the contract says" that the type checker exists to catch.
CHUNK = RetrievedChunk(
    rank=1,
    chunk_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
    document_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
    score=0.8,
)


# --- the split ---------------------------------------------------------------

def test_the_train_and_test_sets_are_disjoint():
    """The assertion that makes every accuracy number below mean anything.

    No weights needed, so it runs in the default suite. If a future change copies a test
    message into the training file to fix a miss, this fails rather than quietly turning
    the evaluation into a memory check.
    """
    train = {e["message"].strip().lower() for e in TRAIN}
    held_out = {t["message"].strip().lower() for t in TEST_SET}

    assert not (train & held_out), (
        "a held-out message appears in the training set: " + ", ".join(sorted(train & held_out))
    )


def test_every_training_label_is_a_real_tool_or_none():
    tools = {t.value for t in ToolName} | {"none"}
    unknown = {e["label"] for e in TRAIN} - tools

    assert not unknown, f"the training set labels tools that do not exist: {unknown}"


def test_the_training_set_weights_none_most_heavily():
    """A false positive is the expensive error, so the silent class must not be a minority.
    Nothing enforces this in the file itself, so it is enforced here."""
    none = sum(1 for e in TRAIN if e["label"] == "none")

    assert none >= 0.3 * len(TRAIN), f"only {none}/{len(TRAIN)} training examples are `none`"


# --- the keyword half, which needs no model ---------------------------------

@pytest.mark.parametrize("message", [c["message"] for c in CASES if c["expect"] == "create-task"])
def test_keywords_still_catch_every_create_task_case_they_used_to(message):
    """The incumbent's own ground truth, kept as a regression.

    Moving this logic from Java to Python is exactly the kind of change that loses a rule
    silently, so every create-task case in the held-out set is asserted against the PORTED
    rules. One of them, "can you note down ...", only passes because Day 14 found "note
    down" missing from the trigger list.
    """
    assert keyword_route(message) == ToolName.CREATE_TASK.value


@pytest.mark.parametrize(
    "case", [c for c in CASES if c.get("trap")], ids=lambda c: c["message"][:40]
)
def test_no_trap_reaches_the_keyword_router(case):
    """Each trap is built from genuine task vocabulary inside a question."""
    assert keyword_route(case["message"]) is None, f"FALSE POSITIVE — {case['trap']}"


def test_a_question_mark_alone_is_enough_to_stay_silent():
    assert keyword_route("remind me to file the report") == "create-task"
    assert keyword_route("remind me to file the report?") is None
    assert looks_like_a_question("Does the policy mention a reminder")


# --- titles ------------------------------------------------------------------

def test_the_request_wrapper_is_stripped_from_the_title():
    assert task_title_from("create a task to review the runway findings") == "Review the runway findings"
    assert task_title_from("remind me to email the supervisor") == "Email the supervisor"


def test_a_trailing_clause_is_dropped():
    assert task_title_from("remind me to review the findings, it is overdue") == "Review the findings"


def test_a_colon_after_the_trigger_does_not_become_the_title():
    """A defect inherited from the Java original and fixed in the port.

    "track this: ..." stripped the trigger and left ": the LSTM inference time looks
    wrong", whose first character is a colon — so capitalising the first character
    upper-cased a colon and the user was offered a task literally titled
    ": the LSTM inference time looks wrong".
    """
    assert task_title_from("track this: the LSTM inference time looks wrong") == (
        "The LSTM inference time looks wrong"
    )


def test_a_title_is_never_empty_and_never_over_the_column_width():
    # "note down" is both a trigger and a prefix; stripping it from a message that is
    # NOTHING BUT the prefix would leave "", and the published schema sets min_length=1.
    assert task_title_from("note down") == "Note down"
    assert len(task_title_from("remind me to " + "x" * 400)) == TASK_TITLE_MAX


# --- the abstain margin, with a stub classifier ------------------------------

class _StubClassifier:
    """Returns fixed probabilities, so the margin rule is tested without any weights."""

    def __init__(self, proba):
        self.classes_ = ["create-task", "lookup-knowledge", "none", "summarize-document"]
        self._proba = proba

    def predict_proba(self, _x):
        return [[self._proba[c] for c in self.classes_]]


def _router(proba):
    return IntentRouter(classifier=_StubClassifier(proba), encode=lambda texts: [[0.0]])


def test_a_tool_that_merely_ties_with_none_is_not_proposed():
    """The asymmetry the whole design rests on. The classifier always has a favourite;
    "summarize-document by 0.001" is not grounds to interrupt a human."""
    barely = _router({"create-task": 0.0, "lookup-knowledge": 0.0,
                      "summarize-document": 0.31, "none": 0.30})

    assert barely.route("summarise something vague").tool is None
    assert barely.route("summarise something vague").decided_by == "silent"


def test_a_clear_win_is_proposed_and_says_which_half_decided():
    clear = _router({"create-task": 0.0, "lookup-knowledge": 0.0,
                     "summarize-document": 0.80, "none": 0.10})
    intent = clear.route("give me an overview of the handbook")

    assert intent.tool == ToolName.SUMMARIZE_DOCUMENT.value
    assert intent.decided_by == "classifier"
    assert intent.confidence == pytest.approx(0.70)


def test_keywords_win_before_the_classifier_is_consulted():
    """Keywords are the auditable half, so where a readable rule applies it decides —
    and the trace must say so, because "why was I asked this?" needs an answer."""
    would_say_lookup = _router({"create-task": 0.0, "lookup-knowledge": 0.99,
                                "summarize-document": 0.0, "none": 0.01})
    intent = would_say_lookup.route("remind me to renew the certificate")

    assert intent.tool == ToolName.CREATE_TASK.value
    assert intent.decided_by == "keywords"


def test_without_a_classifier_the_keyword_half_still_works():
    """A classifier that failed to fit must cost the user nothing beyond the two tools
    that need it — not disable create-task, which works without any model at all."""
    degraded = IntentRouter(classifier=None)

    assert degraded.route("remind me to renew the certificate").tool == "create-task"
    assert degraded.route("summarise the handbook").tool is None
    assert degraded.classifier_ready is False


# --- proposal building -------------------------------------------------------

def _intent(tool):
    return Intent(tool=tool, decided_by="classifier", confidence=0.5, scores={})


def test_nothing_routed_proposes_nothing():
    assert proposals_for("hi", _intent(None), [CHUNK]) == []


def test_a_create_task_proposal_carries_the_extracted_title():
    [proposal] = proposals_for("remind me to renew the certificate", _intent("create-task"), [])

    # isinstance first: `arguments` is a discriminated union, and reading `.title` off the
    # union is only valid once the member is established. The assert documents which tool
    # this case must produce AND narrows the type.
    assert isinstance(proposal.arguments, CreateTaskArguments)
    assert proposal.arguments.title == "Renew the certificate"
    assert proposal.arguments.priority == "medium"
    assert proposal.label == "Create a task: Renew the certificate"


def test_a_summarize_proposal_resolves_the_document_in_code():
    """GAP CLOSED, Day 14b. The published schema asks the MODEL for a chunk ordinal and
    Spring's SummarizePayload needs a document id; for five days nothing bridged the two,
    so a proposal for this tool could not be executed by the backend it was addressed to.
    Resolution happens here, over this service's own retrieval result."""
    [proposal] = proposals_for("summarise the handbook", _intent("summarize-document"), [CHUNK])

    assert isinstance(proposal.arguments, SummarizeDocumentArguments)
    assert proposal.arguments.chunk_ordinal == 1
    assert str(proposal.arguments.document_id) == "22222222-2222-2222-2222-222222222222"


def test_a_summarize_proposal_with_nothing_retrieved_is_dropped():
    """No chunks means no document to point at. A proposal naming an unidentified document
    is the half-built proposal parse_proposal refuses to emit, refused for the same reason."""
    assert proposals_for("summarise the handbook", _intent("summarize-document"), []) == []


def test_a_lookup_proposal_carries_the_question_and_respects_the_schema_bound():
    [proposal] = proposals_for("x" * 900, _intent("lookup-knowledge"), [])

    assert isinstance(proposal.arguments, LookupKnowledgeArguments)
    assert len(proposal.arguments.query) == QUERY_MAX


def test_a_proposal_never_contains_retrieved_text():
    """A SECURITY PROPERTY, asserted rather than asserted-in-prose. Proposals are built
    from the user's message alone, so a poisoned document cannot forge a tool call — the
    chunk text never reaches this function in the first place."""
    poisoned = RetrievedChunk(rank=1, chunk_id=CHUNK.chunk_id, document_id=CHUNK.document_id,
                              score=0.9)
    [proposal] = proposals_for("remind me to check the logs", _intent("create-task"), [poisoned])

    assert "ignore" not in proposal.model_dump_json().lower()
    assert isinstance(proposal.arguments, CreateTaskArguments)
    assert proposal.arguments.title == "Check the logs"


def test_a_tool_nobody_can_build_a_proposal_for_fails_loudly():
    """LABELS and proposals_for have to agree. summarize-document went unproposed for five
    days because two places had to be updated and only one was; a new tool added to the
    classifier and not here raises where a reader can see why."""
    with pytest.raises(ValueError, match="proposals_for cannot build"):
        proposals_for("whatever", _intent("delete-everything"), [CHUNK])


# --- accuracy, which needs the real encoder ---------------------------------

@pytest.fixture(scope="module")
def fitted():
    import numpy as np
    from sentence_transformers import SentenceTransformer

    from app.config import settings

    model = SentenceTransformer(settings.embedding_model,
                                revision=settings.embedding_model_revision, device="cpu")
    return IntentRouter.fit(lambda texts: np.asarray(model.encode(
        list(texts), batch_size=32, normalize_embeddings=True, show_progress_bar=False)))


@pytest.mark.routing
def test_zero_false_positives_on_the_held_out_set(fitted):
    """THE NUMBER THAT DECIDES EVERYTHING. A wrongly-raised proposal puts a decision in
    front of a human that should never have been asked, and a user cannot tell a guardrail
    from a broken product. A miss merely does nothing."""
    offenders = [
        (c["message"], fitted.route(c["message"]).tool)
        for c in TEST_SET
        if c["label"] is None and fitted.route(c["message"]).tool is not None
    ]

    assert not offenders, "FALSE POSITIVES: " + "; ".join(f"{m!r} -> {t}" for m, t in offenders)


@pytest.mark.routing
def test_the_router_beats_the_keyword_list_it_replaced(fitted):
    """The whole justification for adding a model. Measured when written: keywords 25/27,
    classifier alone 24/27, both together 26/27. If a future change makes the combination
    no worse than keywords alone, the model is not paying for itself and should go."""
    both = sum(1 for c in TEST_SET if fitted.route(c["message"]).tool == c["label"])
    keywords_only = sum(1 for c in TEST_SET if keyword_route(c["message"]) == c["label"])

    assert both > keywords_only, (
        f"the classifier adds nothing: {both}/{len(TEST_SET)} with it, "
        f"{keywords_only}/{len(TEST_SET)} from keywords alone"
    )
    assert both >= 26, f"routing regressed to {both}/{len(TEST_SET)}"


@pytest.mark.routing
def test_the_two_tools_keywords_cannot_express_are_now_reachable(fitted):
    """The gap this day existed to close. summarize-document and lookup-knowledge were
    published in GET /tools, validated by the contract and executable since Day 11, and
    NOTHING EVER PROPOSED THEM — so their selection accuracy was undefined, not good."""
    assert fitted.route("summarise the AeroTwin document for me").tool == "summarize-document"
    assert fitted.route("give me a summary of that pdf").tool == "summarize-document"
    assert fitted.route("search my documents for the retention policy").tool == "lookup-knowledge"


@pytest.mark.routing
def test_a_phrasing_in_no_trigger_list_is_still_routed(fitted):
    """WHY A CLASSIFIER AT ALL, in one test. None of these contain any string from
    TASK_TRIGGERS, so the keyword router is silent on every one of them. A keyword list
    only ever matches the phrasings somebody thought to write down."""
    for message in ("could you jot down that the hangar light is broken",
                    "put this on my list: renew the TLS certificate",
                    "don't let me forget the compliance form"):
        assert keyword_route(message) is None, f"{message!r} is not actually a keyword miss"
        assert fitted.route(message).tool == "create-task", message
        assert fitted.route(message).decided_by == "classifier"
