"""The tool registry, published rather than duplicated."""
import hashlib
import json

from fastapi import APIRouter

from app.schemas import (
    CreateTaskArguments,
    LookupKnowledgeArguments,
    SummarizeDocumentArguments,
    ToolDefinition,
    ToolName,
    ToolRegistryResponse,
)

router = APIRouter(tags=["tools"])

# One line per tool, and the ONLY hand-written thing here. Everything else — field names,
# types, bounds, which arguments are required — is generated from the Pydantic model that
# validates the proposal, so the published registry cannot describe a shape the service
# would reject.
_DESCRIPTIONS: dict[ToolName, tuple[str, type]] = {
    ToolName.CREATE_TASK: (
        "Track a piece of work the user asked to be remembered. Spring creates the task row "
        "only after a human approves it.",
        CreateTaskArguments,
    ),
    ToolName.SUMMARIZE_DOCUMENT: (
        "Summarise the document a cited chunk belongs to. The MODEL states only a chunk "
        "ordinal, never an identifier; `document_id` is resolved from it in code before the "
        "proposal leaves this service, and Spring maps that to a filename and re-checks "
        "ownership.",
        SummarizeDocumentArguments,
    ),
    ToolName.LOOKUP_KNOWLEDGE: (
        "Search the user's documents for something the current answer did not cover.",
        LookupKnowledgeArguments,
    ),
}


def _definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(name=name, description=description, arguments_schema=model.model_json_schema())
        for name, (description, model) in _DESCRIPTIONS.items()
    ]


def registry_version(definitions: list[ToolDefinition]) -> str:
    """A fingerprint of the registry's CONTENT, not a number someone remembers to bump.

    A hand-maintained version is a fifth copy of the contract: it drifts the first time a
    field changes and nobody edits the constant. Hashing the published schemas means the
    version changes when, and only when, the thing it versions changes — so Spring can cache
    a registry and detect staleness without this service tracking who has what.
    """
    payload = json.dumps(
        [d.model_dump(mode="json") for d in definitions], sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


@router.get(
    "/tools",
    response_model=ToolRegistryResponse,
    summary="The tool schemas this service may propose. Read-only",
)
def tools() -> ToolRegistryResponse:
    """The registry, published rather than duplicated.

    Spring needs to know what a proposal can look like in order to validate one, and the
    Day 14 evaluation set needs it to assert that a tool is NOT proposed for an unrelated
    request. Both would otherwise keep their own copy of the tool list — which is the
    four-copies problem starting over on its fifth copy.

    GET, and nothing here executes. Proposals are produced alongside an answer; execution is
    Spring's governance flow, never this service.

    THIS REGISTRY DESCRIBED TOOLS NOBODY PROPOSED, FOR FIVE DAYS. Until Day 14b the only
    router in the system was a keyword trigger list in Spring that could emit `create-task`
    and nothing else, so `summarize-document` and `lookup-knowledge` were published here,
    validated by the contract and executable since Day 11 — and unreachable. Their selection
    accuracy was undefined, not good.

    Day 10 had measured the GENERATION model on the routing decision and found a constant
    function: propose-v1 answered "none" to all nine cases including four explicit task
    requests, and propose-v2 answered "create-task" to all nine including "what is the fleet
    size". That retired the idea of a prompt deciding, and `app.intent` replaces it with a
    CLASSIFIER over the retrieval encoder — which is a different thing entirely, and which
    made both of the other two tools reachable.

    AND IT HAD NO CONSUMER. A registry published so the tool list would stop being copied by
    hand, that nothing ever read, prevents nothing. ToolRegistryConformanceTest in the Spring
    suite is its first reader, and tests/test_intent.py is the second.
    """
    definitions = _definitions()
    return ToolRegistryResponse(tools=definitions, registry_version=registry_version(definitions))
