"""Day 1 tests.

Nothing here tests RAG, because nothing does RAG yet. These test the parts of the
contract that already exist and that a later implementation could silently break:
the health split, the empty-list rule, and drift.
"""
from uuid import uuid4

ANSWER = "/answer"


def test_liveness_does_not_depend_on_models(client):
    """Models are not loaded in this suite. Liveness must still be 200 — that is the
    whole distinction between liveness and readiness."""
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "live"}


def test_readiness_is_503_when_models_are_not_loaded(client):
    r = client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "MODEL_NOT_READY"


def test_trace_id_is_echoed(client):
    r = client.get("/health/live", headers={"X-Trace-Id": "abc123"})
    assert r.headers["X-Trace-Id"] == "abc123"


def test_omitted_allowed_document_ids_is_422(client):
    """Omission is Spring's bug and must be loud. There is no default."""
    r = client.post(ANSWER, json={"question": "anything"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "MALFORMED_REQUEST"
    assert any("allowed_document_ids" in e["field"] for e in r.json()["detail"]["errors"])


def test_empty_allowed_document_ids_is_accepted(client):
    """The rule this suite exists to protect.

    An empty list is a NORMAL state — a user with no ready documents. It must reach the
    handler, not be rejected.

    Day 7 update, exactly as this docstring predicted: /answer is implemented, so the
    status is no longer 501. This suite loads no models, so the request now gets as far as
    the readiness check and stops at 503 MODEL_NOT_READY. Against a running service it
    reaches retrieval and returns insufficient_context.

    The invariant never changes and is what the assertion actually protects: **not 422.**
    Rejecting empty would push the caller toward `if allowed_ids:` at the query, and that
    branch is the leak — an empty list would silently become a search across every user's
    documents.
    """
    r = client.post(ANSWER, json={"question": "anything", "allowed_document_ids": []})
    assert r.status_code != 422, "empty allowed_document_ids must be accepted, not rejected"
    assert r.status_code == 503, "models are not loaded in this suite"
    assert r.json()["detail"]["code"] == "MODEL_NOT_READY"


def test_unknown_field_is_rejected(client):
    """extra='forbid'. Drift should fail on the first request, not go unnoticed for weeks."""
    r = client.post(ANSWER, json={
        "question": "anything",
        "allowed_document_ids": [str(uuid4())],
        "temperature": 0.7,
    })
    assert r.status_code == 422
    assert any("temperature" in e["field"] for e in r.json()["detail"]["errors"])


def test_tool_registry_is_declared(client):
    """Day 1 declared the tool API and Day 10 implemented it, exactly as this docstring
    anticipated — so the assertion moves from 501 to a real registry. The shape it was
    guarding is unchanged and is now covered in detail by tests/test_tools.py."""
    r = client.get("/tools")
    assert r.status_code == 200
    body = r.json()
    assert {t["name"] for t in body["tools"]} == {"create-task", "summarize-document",
                                                  "lookup-knowledge"}
    assert body["registry_version"]


def test_answer_response_declares_tool_proposals():
    """Proposals ride WITH the answer. If this field is ever moved to its own endpoint, the
    trace splits across two requests and Day 18's observability gets harder, so the shape is
    pinned by a test rather than by memory."""
    from app.schemas import AnswerResponse, ToolProposal

    field = AnswerResponse.model_fields["proposals"]
    assert field.default_factory is list, "proposals must default to empty, never be required"
    assert "ToolProposal" in str(field.annotation)
    assert ToolProposal.model_fields["arguments"].discriminator == "tool", (
        "arguments must stay a union discriminated on `tool`"
    )


def test_tool_arguments_are_a_discriminated_union_not_a_free_form_map():
    """BACKLOG.md item 2: Spring's outbound payload is an untyped Map<String,Object>, so a
    typo in a key is invisible until the frontend misreads it. This boundary does not repeat
    that — an unknown tool or a bad argument is a validation error, not a silent pass.

    Note the hyphens: these are Spring's ActionType strings, the ones written to Postgres
    and matched by the frontend's discriminated union. "create_task" is now a rejected tag,
    which is the point — the naming cannot drift silently.
    """
    import pytest
    from pydantic import ValidationError

    from app.schemas import CreateTaskArguments, ToolProposal

    ok = ToolProposal.model_validate({
        "label": "Create a tracking task",
        "arguments": {"tool": "create-task", "title": "Summarise the leave policy", "priority": "high"},
    })
    assert isinstance(ok.arguments, CreateTaskArguments)  # narrows the union for the checker
    assert ok.arguments.priority == "high"

    with pytest.raises(ValidationError):
        ToolProposal.model_validate({
            "label": "Do something",
            "arguments": {"tool": "delete_everything"},
        })


def test_a_dead_loader_thread_reports_failed_not_loading(monkeypatch):
    """Regression: readiness must never report "loading" for a loader that has stopped.

    Before the fix, `import torch` and set_num_threads sat outside both try blocks, so an
    error there killed the thread with both states still LOADING — and /health/ready said
    "still loading" forever. A dead service that looks like a slow one is worse than one
    that looks dead, because nobody investigates a slow start.
    """
    from app.models_registry import ModelRegistry
    from app.schemas import ModelState

    registry = ModelRegistry()
    monkeypatch.setattr(registry, "_load_embedding", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    registry.start_loading().join(timeout=10)

    assert registry.embedding_state is ModelState.FAILED
    assert registry.generation_state is ModelState.FAILED
    assert "loader thread died" in registry.status_message() or "boom" in registry.status_message()
    assert "loading" not in registry.status_message().replace("loader", "")


# --- ordinals are 1-based everywhere, Day 6 ---------------------------------

def test_every_ordinal_in_the_contract_is_one_based():
    """One field said `ge=0, "0-based"` and everything else said 1-based.

    Chunking starts at 1, Postgres enforces CHECK (ordinal >= 1), live rows run 1..24,
    and contract revision 7 says 1-based. The disagreeing field was the one PUBLISHED in
    /openapi.json, so it was the copy Spring's hand-written client would have been built
    against — and Java list access is 0-indexed, which turns "0-based" into a silent
    off-by-one on every citation.
    """
    import pytest

    from app.schemas import Chunk, SummarizeDocumentArguments

    # Citation is deliberately absent: Day 7 REMOVED its ordinal, because no consumer
    # exists — not the citations table, not CitationDto, not Type.ts. See the next test.
    for model, kwargs in (
        (Chunk, {"text": "t", "token_count": 1, "char_start": 0, "char_end": 1, "embedding": []}),
        (SummarizeDocumentArguments, {}),
    ):
        field = "chunk_ordinal" if model is SummarizeDocumentArguments else "ordinal"
        # 1 is the first legal value...
        model(**{**kwargs, field: 1})
        # ...and 0 must be rejected by the CONTRACT, not later by a Postgres CHECK.
        with pytest.raises(ValueError):
            model(**{**kwargs, field: 0})


def test_published_spec_never_describes_an_ordinal_as_zero_based(client):
    """The description ships to callers. It is documentation with consequences."""
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name, schema in schemas.items():
        for field, spec in schema.get("properties", {}).items():
            if "ordinal" in field:
                assert spec.get("minimum") == 1, f"{name}.{field} allows ordinal 0"
                assert "0-based" not in spec.get("description", ""), f"{name}.{field}"


def test_citation_carries_no_ordinal_because_nothing_reads_one():
    """Verified against all three consumers on Day 7, not assumed:

        citations table   -> {message_id, document_id, section, excerpt}, no ordinal column
        CitationDto.java  -> id, documentId, documentName, section, excerpt
        Type.ts Citation  -> the same five fields

    Spring hydrates excerpt and section from the `document_chunks` row that `chunk_id`
    identifies, so an ordinal is redundant for lookup and read by nobody.
    """
    from app.schemas import Citation

    assert "ordinal" not in Citation.model_fields
    # `quote` was added on Day 9: the sentence FROM THE CHUNK that the model's quote
    # matched. Still no ordinal — nothing reads one.
    assert set(Citation.model_fields) == {"chunk_id", "document_id", "score", "quote"}
