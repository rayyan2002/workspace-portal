"""Every request and response shape on the Spring <-> GenAI boundary.

These models are the contract. FastAPI validates incoming requests against them and
generates /openapi.json from them, so the published spec cannot disagree with what the
server accepts. That is the whole reason this service is FastAPI and not Flask.

The spec does NOT stop drift by itself — Spring's client is hand-written until it is
generated from this spec or checked against it in a test. See BACKLOG.md.
"""
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings


class Strict(BaseModel):
    """extra='forbid' everywhere.

    If Spring sends a field this service does not know about, that is drift, and drift
    should be a 422 on the first request rather than a value silently ignored for weeks.
    Month 2's contract rotted precisely because mismatches were survivable.
    """

    model_config = ConfigDict(extra="forbid")


# --- errors -----------------------------------------------------------------

class ErrorCode(str, Enum):
    MODEL_NOT_READY = "MODEL_NOT_READY"
    MALFORMED_REQUEST = "MALFORMED_REQUEST"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorDetail(Strict):
    code: ErrorCode
    message: str
    trace_id: str
    errors: list[dict] | None = Field(default=None, description="Field-level detail for MALFORMED_REQUEST")


class ErrorResponse(Strict):
    detail: ErrorDetail


# --- health -----------------------------------------------------------------

class ModelState(str, Enum):
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


class LiveResponse(Strict):
    status: str = "live"


class ReadyResponse(Strict):
    status: str = "ready"
    embedding_model: str
    embedding_model_revision: str
    embedding_dim: int
    generation_model: str
    generation_model_revision: str


# --- ingestion --------------------------------------------------------------

class IngestTrace(Strict):
    trace_id: str
    extract_ms: int
    chunk_ms: int
    embed_ms: int
    total_ms: int


class Chunk(Strict):
    ordinal: int = Field(
        ge=1,
        description="Order within the document, 1-based. The first chunk is 1, never 0",
    )
    text: str
    token_count: int = Field(ge=1, description="Measured with the embedding model's tokenizer")
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    section: str | None = Field(
        default=None,
        max_length=255,
        description="Heading or sheet name the chunk came from. Maps to document_chunks.section",
    )
    page: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Page number for paged formats. Revision 7 recorded these two fields as added on "
            "Day 3 and they were NOT — the ingestion dataclass, the database column and the "
            "citation card all carry them, and only the published contract did not. Caught on "
            "Day 11c while implementing /ingest: without them every newly uploaded document "
            "would store NULL, and Day 9's 'Page N' line would be blank for uploads while "
            "working for the fixture-loaded corpus"
        ),
    )
    embedding: list[float] = Field(description="Exactly embedding_dim floats")


class IngestResponse(Strict):
    document_id: UUID
    chunk_count: int = Field(ge=0)
    embedding_model: str
    embedding_model_revision: str
    chunking_strategy: str = Field(
        description=(
            "How these chunks were cut: 'sentence' packs whole sentences to the token "
            "ceiling, 'semantic' cuts where neighbouring meaning diverges. Spring stores "
            "it per chunk (V24) so a mixed corpus can say which rows are which."
        ),
    )
    embedding_dim: int
    chunks: list[Chunk]
    trace: IngestTrace


# --- tool proposals ---------------------------------------------------------
#
# Declared on Day 1, designed on Day 10. Two rules are fixed now because they are
# boundary rules, not tool-design details:
#
#   1. Python PROPOSES. It never executes, and it never writes. An approved proposal is
#      executed by Spring's existing governance flow, which already writes an audit row
#      for every decision including rejections. Fails closed.
#   2. Arguments are a DISCRIMINATED UNION, not a free-form map. BACKLOG.md item 2 records
#      that Spring's outbound `Map<String, Object>` payload has no schema, so a typo in a
#      key is invisible until the frontend misreads it. This side does not repeat that.

class ToolName(str, Enum):
    """Values match Spring's ActionType enum EXACTLY — hyphens, not underscores.

    ActionType writes these literal strings to PostgreSQL (`action_audit.type`), Jackson
    dispatches on them via @JsonSubTypes, and the frontend's discriminated union in
    Type.ts matches on them. The training tracker writes them with underscores; the
    running system does not, and the running system wins. Emitting "create_task" here
    would have required a translation layer whose only job is to undo a naming choice —
    i.e. a fifth hand-maintained copy of the contract.
    """

    CREATE_TASK = "create-task"
    SUMMARIZE_DOCUMENT = "summarize-document"
    LOOKUP_KNOWLEDGE = "lookup-knowledge"


class CreateTaskArguments(Strict):
    """Mirrors Spring's CreateTaskPayload exactly: title + priority, nothing else.

    `description` was here and has been removed: no consumer exists. Spring's payload does
    not accept it, the tasks table has no column for it, and the frontend's ActionProposal
    union does not read it. An extra field with no consumer is how the four-copies drift
    started in Month 2 — this one was two days old.

    max_length 255 matches `tasks.title VARCHAR(255)`, so an over-long title is rejected
    here rather than surfacing from Postgres as a 500.
    """

    tool: Literal[ToolName.CREATE_TASK] = ToolName.CREATE_TASK
    title: str = Field(min_length=1, max_length=255)
    priority: Literal["low", "medium", "high"] = Field(
        description="Matches TaskPriority. Month 2 hardcoded 'medium'; Month 3 infers it"
    )


class SummarizeDocumentArguments(Strict):
    """TWO FIELDS WITH TWO DIFFERENT AUTHORS, which is the whole point of this class.

    `chunk_ordinal` is what a MODEL may state. `document_id` is what CODE resolved it to.
    Nothing produces both, and the distinction is load-bearing: this service must never ask
    the model for a document id, because a UUID costs 36 tokens and measurably stops the
    0.5B model citing at all, and it cannot know a filename it was never shown.

    So the chain is: the model quotes a sentence -> `resolve_quote` turns the quote into a
    1-based ordinal over the chunks ACTUALLY SENT -> this service looks that ordinal up in
    its own retrieval result and fills in `document_id`. Every step after the quote is
    arithmetic over data this service already holds.

    `document_id` was missing until Day 14b and that was the gap: INTEGRATION_CONTRACT.md
    §5 specified the ordinal-to-document translation, Spring's SummarizePayload needs
    {documentId, documentName}, and NOTHING PERFORMED THE TRANSLATION. Jackson failed
    closed on the mismatch — loudly, with "Unrecognized field", rather than nulling — so it
    was latent rather than silent, but a proposal for this tool could not have been
    executed by the backend it was addressed to.

    Spring still derives `documentName` from its own `documents` row and RE-CHECKS
    OWNERSHIP rather than trusting this field. A document id arriving over HTTP is a claim;
    Spring owns that table and is the only side that can verify it.
    """

    tool: Literal[ToolName.SUMMARIZE_DOCUMENT] = ToolName.SUMMARIZE_DOCUMENT
    chunk_ordinal: int = Field(
        ge=1, description="1-based index into the chunks sent for this request. Resolved from a quote"
    )
    document_id: UUID | None = Field(
        default=None,
        description=(
            "The document the cited chunk belongs to, RESOLVED IN CODE from chunk_ordinal — "
            "never stated by the model. Null only inside this service before resolution; a "
            "proposal that still has null here is dropped rather than sent"
        ),
    )


class LookupKnowledgeArguments(Strict):
    """Mirrors Spring's LookupPayload: a single query string."""

    tool: Literal[ToolName.LOOKUP_KNOWLEDGE] = ToolName.LOOKUP_KNOWLEDGE
    query: str = Field(min_length=1, max_length=500)


ToolArguments = Annotated[
    CreateTaskArguments | SummarizeDocumentArguments | LookupKnowledgeArguments,
    Field(discriminator="tool"),
]


class ToolProposal(Strict):
    """No id field, deliberately.

    Verified against the running backend: Spring emits `"id": "act-<uuid>"` — a STRING with
    an `act-` prefix, not a bare UUID — and that value becomes `action_audit.action_id`
    (VARCHAR(255)) when a decision is recorded. Spring owns that row, so Spring mints the
    id. A `proposal_id: UUID` here would have been a second, conflicting identity for the
    same thing, and Spring would have had to discard it.

    `label` is what the user actually reads on the approve/reject control: the frontend's
    ActionProposal union in Type.ts requires it, and Spring currently hardcodes
    "Create a tracking task for this request". Month 3 can do better than a constant, which
    is why the model supplies it rather than the backend.
    """

    arguments: ToolArguments
    label: str = Field(
        min_length=1,
        max_length=120,
        description="Shown on the approve/reject control. Maps to ActionProposalDto.label",
    )


class ToolDefinition(Strict):
    """One entry in the registry published by GET /tools."""

    name: ToolName
    description: str
    arguments_schema: dict = Field(description="JSON Schema for this tool's arguments")


class ToolRegistryResponse(Strict):
    tools: list[ToolDefinition]
    registry_version: str


# --- retrieval and answering ------------------------------------------------

class ConversationTurn(Strict):
    """One earlier message in the same conversation.

    Spring owns the `messages` table and sends these; Python stays stateless and
    `session_id` remains correlation-only, never looked up. Keeping history in the REQUEST
    rather than having Python query for it preserves rule R1 — this service holds SELECT on
    the chunk tables and nothing else — and keeps the service a pure function of its input,
    which is what makes a bad answer reproducible from the trace alone.
    """

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class RetrievalRequest(Strict):
    """Shared by /answer and /retrieve.

    allowed_document_ids is REQUIRED and has NO DEFAULT, and an empty list is LEGAL.

      omitted -> 422. Spring always knows the answer, so omission is a Spring bug and
                 should be loud.
      empty   -> a normal state (a user with no ready documents). Zero chunks, and
                 outcome=insufficient_context.

    Do not add `= []` here, and do not write `if allowed_document_ids:` at the query.
    That branch is the leak: with it, an empty list silently becomes an unfiltered
    search across every user's documents. The filter is applied unconditionally.
    Spring computes this list as documents that are owned AND ready.
    """

    question: str = Field(min_length=1, max_length=4000)
    allowed_document_ids: list[UUID]
    # Defaults come FROM config, they are not retyped here. These values are published in
    # /openapi.json and read by Spring, so a literal here would be a second copy that
    # drifts the moment config changes — which is exactly what happened to min_score:
    # config said one thing, the contract another, and the contract is what callers see.
    top_k: int = Field(default=settings.default_top_k, ge=1, le=50)
    min_score: float = Field(
        default=settings.default_min_score,
        ge=-1.0,
        le=1.0,
        description="Cosine SIMILARITY, higher is better",
    )
    session_id: UUID | None = Field(default=None, description="Correlation only; never looked up")
    model: Literal["local", "gemini"] | None = Field(
        default=None,
        description=(
            "Which generation backend answers. Omitted means the configured default, which "
            "is `local`. CHOOSING `gemini` SENDS THE RETRIEVED CHUNKS — the user's private "
            "documents — TO GOOGLE; `local` keeps everything on the machine. That is why "
            "this is per request and reported back in the trace, rather than configured "
            "once and forgotten. Retrieval, citations and every guardrail are identical "
            "either way; only the step that turns a prompt into text differs"
        ),
    )
    include_raw: bool = Field(
        default=False,
        description=(
            "DIAGNOSTIC. Populates trace.raw_model_reply with the model's verbatim output "
            "before any parsing. Off by default and Spring never sets it: the raw reply can "
            "run to several KB of half-formed JSON and is of no use to a product request. "
            "It exists so 'the model said X but the user saw Y' is answerable at all — "
            "benchmarks/19 sets it"
        ),
    )
    history: list[ConversationTurn] = Field(
        default_factory=list,
        max_length=50,
        description=(
            "Earlier turns in this conversation, oldest first. UNLIKE allowed_document_ids "
            "this DOES default to empty, because absent and empty mean the same thing here — "
            "the first turn of a conversation has no history, and that is not a Spring bug. "
            "Truncated to the most recent settings.max_history_turns in code; the 50 cap is a "
            "sanity bound, not the working limit"
        ),
    )


class RetrievedChunk(Strict):
    rank: int = Field(ge=1)
    chunk_id: UUID
    document_id: UUID
    score: float = Field(description="Cosine similarity in [-1, 1]. NOT pgvector distance")


class Citation(Strict):
    """No `ordinal`, and no text.

    `ordinal` was here until Day 7 and had NO CONSUMER — verified against all three rather
    than assumed:

        citations table   -> {message_id, document_id, section, excerpt}, no ordinal column
        CitationDto.java  -> id, documentId, documentName, section, excerpt
        Type.ts Citation  -> the same five fields

    Spring resolves everything it needs from `chunk_id`: the `document_chunks` row holds
    the text it renders as `excerpt` and the `section` the card shows. An ordinal is
    redundant for lookup and read by nobody. Same rule that removed `description` from
    CreateTaskArguments on Day 2 — an extra field with no consumer is how the four-copies
    drift started in Month 2.

    Day 6 corrected this field's floor from `ge=0` to `ge=1` without asking whether the
    field should exist at all. The correction was right on its own terms; the question was
    simply not asked until Day 7.

    No text either, for the Day 1 reason: Spring wrote the chunk rows and hydrates excerpts
    from its own database rather than trusting this service to echo them back.
    """

    chunk_id: UUID
    document_id: UUID
    score: float
    quote: str = Field(
        default="",
        description=(
            "The sentence FROM THE CHUNK that the model's quote resolved to — the document's "
            "words, never the model's. This is what a citation card shows: the whole chunk "
            "averages 1,538 characters and reaches 2,597, which is a dump rather than "
            "something a reader can inspect. Empty when no single sentence stood out, in "
            "which case Spring falls back to the stored chunk text"
        ),
    )


class Outcome(str, Enum):
    GROUNDED = "grounded"
    INSUFFICIENT_CONTEXT = "insufficient_context"


class SpellingCorrection(Strict):
    """One word replaced before the search that produced this answer.

    An OBJECT rather than a two-element array on purpose: this crosses into Jackson and
    then into hand-written TypeScript, and `{typed, used}` survives both without anyone
    having to remember which end of a pair is which.
    """

    typed: str = Field(description="What the user wrote")
    used: str = Field(description="The corpus word it was searched as")


class RetrieveTrace(Strict):
    trace_id: str
    retrieved: list[RetrievedChunk] = Field(description="EVERY retrieved chunk, including uncited ones")
    top_k: int
    min_score: float
    candidates_before_threshold: int = Field(
        description="Distinct candidates AFTER duplicate collapsing, BEFORE min_score"
    )
    collapsed_duplicates: int = Field(
        default=0,
        description=(
            "Rows dropped as byte-identical duplicates of a higher-ranked chunk. Without "
            "this number, collapsing is invisible: a top_k of 5 that returns 2 chunks looks "
            "identical to a corpus with only 2 matches"
        ),
    )
    retrieval_mode: str = Field(
        default="similarity",
        description=(
            "`similarity` — chunks ranked by closeness to the question, the normal path. "
            "`document_summary` — the request was routed to summarize-document, so the "
            "chunks are the OPENING of the best-matching document in document order "
            "instead. Without this field the two paths are indistinguishable in a trace, "
            "and they answer different questions"
        ),
    )
    filename_tiebreak: bool = Field(
        default=False,
        description=(
            "Two documents scored within min_document_margin and the question named one of "
            "them outright. See app/selectivity.py."
        ),
    )

    rare_term_rescue: list[str] = Field(
        default_factory=list,
        description=(
            "Query terms that named a document the vector search had not picked. Non-empty "
            "only when the rescue changed the result; see app/selectivity.py."
        ),
    )

    spelling_corrections: list["SpellingCorrection"] = Field(
        default_factory=list,
        description=(
            "Words corrected before the search that produced this answer, as [typed, used]. "
            "Present only when the question as typed retrieved NOTHING and the corrected one "
            "retrieved something — so a user can be told what was assumed instead of being "
            "silently answered about a different word"
        ),
    )
    best_rejected_score: float | None = Field(
        default=None,
        description=(
            "When NOTHING cleared min_score, the highest score that failed it. Separates a "
            "near miss from a question the corpus has never heard of — 'tell me about ai "
            "saftey' scores 0.5355 where the correct spelling scores 0.7120, and without "
            "this the caller cannot tell the user that their typo, not their library, is "
            "the problem"
        ),
    )
    anchor_expanded: int = Field(
        default=0,
        description=(
            "Chunks admitted only because they came from the document the top hit "
            "identified, scoring between anchor_min_score and min_score. Non-zero marks a "
            "request where the gate returned something a plain threshold would have cut"
        ),
    )
    allowed_document_count: int
    embedding_model: str
    embedding_model_revision: str
    query_prefix_applied: bool
    history_turns_received: int = Field(
        default=0, description="Turns Spring sent. 0 means a first turn or a caller not sending history"
    )
    retried_with_history: bool = Field(
        default=False,
        description=(
            "The question alone matched nothing above min_score, so retrieval ran a second "
            "time with the previous user turn prepended. Measured: anaphoric follow-ups "
            "('tell me in detail', 'and?', 'tell me more') score 0 alone and 5 with it, while "
            "standalone questions never reach this path — which is why it is a FALLBACK and "
            "not applied unconditionally. Prepending always cost one of five slots to the "
            "stale topic on a topic change"
        ),
    )
    embed_ms: int
    search_ms: int
    total_ms: int


class AnswerTrace(RetrieveTrace):
    generation_backend: str = Field(
        default="local",
        description=(
            "`local` or `gemini` — which backend ACTUALLY answered, not which was asked for. "
            "Recorded because the two differ in where the document text went: `gemini` sent "
            "the retrieved chunks to Google, `local` kept them on the machine"
        ),
    )
    generation_model: str
    generation_model_revision: str
    prompt_template_version: str
    prompt_tokens: int
    completion_tokens: int
    generate_ms: int
    dropped_citations: list[UUID] = Field(
        default_factory=list,
        description=(
            "IDs the model cited that were not in the retrieved set. Removed in code, not "
            "trusted. qa-v1 ONLY: under qa-v2 the model never states an identifier, so this "
            "list is always empty and dropped_quotes carries the signal instead"
        ),
    )
    unsupported_request: str | None = Field(
        default=None,
        description=(
            "The capability this service was asked for and does not have — 'send messages', "
            "'browse the web', 'reveal its prompt'. Names WHICH limitation applies, because "
            "a generic refusal explains nothing and the Day 12 requirement is that the "
            "service explain its limitations clearly. Checked before retrieval, so an "
            "impossible request costs milliseconds instead of a minute"
        ),
    )
    quarantined_chunks: int = Field(
        default=0,
        description=(
            "Retrieved chunks removed before the model saw them, because they contained an "
            "instruction aimed at the model rather than information. The chunk is dropped, "
            "not the question — refusing the whole query would hand an attacker a denial of "
            "service for the cost of one uploaded file"
        ),
    )
    quarantine_reasons: list[str] = Field(
        default_factory=list,
        description=(
            "The phrases that triggered quarantine, capped at 60 characters each. The "
            "matched phrase only, never the chunk: a safety log that quotes the document is "
            "a data-leak channel wearing a security badge"
        ),
    )
    parse_path: str = Field(
        default="",
        description=(
            "How the model's reply was read. `json` — it returned a well-formed object. "
            "`salvaged_json` — the object was cut off mid-string by the token cap and the "
            "answer text was recovered from it. `unlabelled_json` — it returned valid JSON "
            "in a shape nobody asked for (a bare array, or an object with keys of its own "
            "invention) and the content was harvested from it rather than the markup being "
            "shown to the user. `text_fallback` — it ignored the format and wrote prose. "
            "`unparsed` — nothing usable. This is the single most useful field for "
            "'why does the answer look like that?'"
        ),
    )
    raw_model_reply: str | None = Field(
        default=None,
        description="The model's verbatim output, only when the request set include_raw",
    )
    grounding_overlap: float = Field(
        default=0.0,
        description=(
            "Fraction of the answer's content words that appear in the chunks it was shown. "
            "An answer built from the context scores 0.58-1.00; one written from the model's "
            "training scores near zero. Reported always, so a borderline answer is visible "
            "even when it was allowed through"
        ),
    )
    rejected_as_ungrounded: bool = Field(
        default=False,
        description=(
            "The retrieval cleared min_score but the ANSWER was not made of the retrieved "
            "text, so it was withheld and the outcome downgraded to insufficient_context. "
            "This is the guard against a confident answer with no source — the same rule as "
            "dropping an unresolvable citation, applied to the whole reply"
        ),
    )
    citation_source: str = Field(
        default="none",
        description=(
            "`quotes` | `answer_fallback` | `none`. WHICH MECHANISM produced the citations. "
            "`quotes` is the model naming the sentence it used — the strongest evidence, and "
            "what qa-v2 is built around. `answer_fallback` is this service locating the "
            "ANSWER's own sentences in the retrieved chunks afterwards, which runs only when "
            "the model declared none: Qwen2.5-0.5B keeps to the JSON envelope on short "
            "factual questions and abandons it on open-ended ones, so a 0.73-overlap answer "
            "was shipping with zero sources. Both ship the DOCUMENT's words; they are not "
            "equally strong evidence, and a surprising citation must be traceable to the "
            "weaker mechanism"
        ),
    )
    routed_tool: str | None = Field(
        default=None,
        description=(
            "Which tool the router chose for this message, or null for none. Day 14b made "
            "this answerable: 'why was I offered this?' had no answer in the trace while "
            "routing lived in a keyword list in another service"
        ),
    )
    routed_by: str = Field(
        default="silent",
        description=(
            "`keywords` | `classifier` | `silent` | `suppressed` | `failed`. WHICH HALF "
            "DECIDED, and it is a question that had no answer in the trace while routing "
            "lived in a keyword list in another service. The "
            "router is a trigger list AND a classifier over the retrieval encoder, and an "
            "operator reading a surprising proposal needs to know which one to go and look "
            "at. `suppressed` means the question was an unsupported request, so routing "
            "was not consulted at all"
        ),
    )
    routing_confidence: float | None = Field(
        default=None,
        description=(
            "The classifier's margin over its `none` probability; 1.0 for a keyword hit. A "
            "tool is only proposed when this clears 0.10, because a favourite that wins by "
            "0.001 is not grounds to interrupt a human"
        ),
    )
    dropped_quotes: list[str] = Field(
        default_factory=list,
        description=(
            "Quotes the model attributed to the context that could not be matched back to "
            "any chunk shown — paraphrase, invention, or an ambiguous tie between two "
            "chunks. Under qa-v2 this is the real drop signal: the model never states an "
            "identifier, so dropped_citations above cannot populate. Truncated to 60 "
            "characters, so it is never a channel for chunk text"
        ),
    )
    dropped_proposals: list[str] = Field(
        default_factory=list,
        description=(
            "Tool proposals rejected before they left this service — unknown tool, arguments that "
            "failed validation, or a document_id outside allowed_document_ids. Same rule as citations: "
            "a small model's output is checked in code, never trusted"
        ),
    )


class RetrieveResponse(Strict):
    """No text. Spring wrote the chunk rows and hydrates excerpts from its own database."""

    retrieved: list[RetrievedChunk]
    trace: RetrieveTrace


class AnswerResponse(Strict):
    outcome: Outcome
    answer: str = Field(description="Empty string when outcome is insufficient_context")
    citations: list[Citation]
    proposals: list[ToolProposal] = Field(
        default_factory=list,
        description=(
            "Returned WITH the answer rather than from a second endpoint: a separate call would "
            "re-run retrieval and split the trace across two requests. Spring's governance flow "
            "decides whether any of these execute; nothing here has run"
        ),
    )
    trace: AnswerTrace
