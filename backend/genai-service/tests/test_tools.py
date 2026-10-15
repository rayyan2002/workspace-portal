"""Day 10: the published tool registry.

The registry exists so Spring and the Day 14 evaluation set stop keeping private copies of
the tool list. Its value depends entirely on it not drifting from the models that validate
a proposal, which is what these tests hold.
"""
from app.routers.tools import _definitions, registry_version
from app.schemas import CreateTaskArguments, ToolName


def test_every_declared_tool_is_published(client):
    body = client.get("/tools").json()
    assert {t["name"] for t in body["tools"]} == {t.value for t in ToolName}


def test_tool_names_are_hyphenated_exactly_as_springs_action_type(client):
    """These literals go to Postgres (action_audit.type), to Jackson's @JsonSubTypes, and to
    the frontend's discriminated union. The tracker writes them with underscores; the
    running system does not, and the running system wins."""
    names = {t["name"] for t in client.get("/tools").json()["tools"]}
    assert names == {"create-task", "summarize-document", "lookup-knowledge"}
    assert not any("_" in name for name in names)


def test_the_published_schema_is_generated_from_the_validating_model(client):
    """Not hand-written. A registry that describes a shape the service would reject is
    worse than no registry, because Spring would build against the description."""
    published = next(t for t in client.get("/tools").json()["tools"] if t["name"] == "create-task")
    assert published["arguments_schema"] == CreateTaskArguments.model_json_schema()


def test_the_published_constraints_match_the_database(client):
    """max_length 255 is `tasks.title VARCHAR(255)`; the priority enum is TaskPriority. A
    proposal that satisfies the published schema must be storable."""
    schema = next(t for t in client.get("/tools").json()["tools"]
                  if t["name"] == "create-task")["arguments_schema"]

    assert schema["properties"]["title"]["maxLength"] == 255
    assert schema["properties"]["priority"]["enum"] == ["low", "medium", "high"]
    assert set(schema["required"]) == {"title", "priority"}


def test_the_version_is_a_fingerprint_of_the_content():
    """A hand-bumped version is a fifth copy of the contract: it drifts the first time a
    field changes and nobody edits the constant."""
    definitions = _definitions()
    assert registry_version(definitions) == registry_version(_definitions())

    changed = list(definitions)
    changed[0] = changed[0].model_copy(update={"description": "something else"})
    assert registry_version(changed) != registry_version(definitions)


def test_the_registry_is_read_only(client):
    """Nothing here executes. Proposals travel with an answer; execution is Spring's
    governance flow, and this endpoint must never grow a verb."""
    assert client.post("/tools").status_code == 405
