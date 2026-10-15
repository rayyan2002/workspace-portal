# Spring ↔ GenAI Integration Contract

**Status:** written on Day 1 of Month 3, *before* the service does anything. Every endpoint below is declared and returns **`501 Not Implemented`** today. The shapes are real; the behaviour is not.

This document exists because of Month 2's largest piece of debt. The frontend–backend contract lived in four hand-maintained copies that drifted independently, and every drift was found by accident. This boundary starts with one written contract and one machine-readable spec (`/openapi.json`, generated from the same Pydantic models that validate requests).

> **The spec does not prevent drift by itself.** Spring's client is hand-written until it is generated from this spec or checked against it in a test. That check is the fix; the spec is only the foundation for it. Tracked in `BACKLOG.md`.

---

## 0. Deviation from the training tracker

The tracker specifies **Flask** in every Month 3 row. This service is **FastAPI**. The deviation is deliberate and was decided on Day 1, not discovered later.

1. *Primary:* familiarity. The web framework is the thinnest layer of this service — a few routes around the actual work. The month's learning budget goes to chunking, embeddings, retrieval, grounded answers and tool calling, not to an unfamiliar HTTP layer.
2. *Secondary:* FastAPI derives its OpenAPI spec from the same Pydantic models that validate requests, so the spec cannot disagree with the server. Flask reaches the same place with extensions, bolted on rather than built in.

What was learned this month is the RAG pipeline, not the framework. Day 21's framework-transfer reflection should cover what the Flask version would have looked like.

---

## 1. Shape of the boundary

```
React ──▶ Spring Boot ──▶ FastAPI service
              │                 ┆
        reads + writes      SELECT only
              ▼                 ▼
        PostgreSQL + pgvector (Flyway owns the schema)
```

Five rules. Everything else in this document follows from them.

| # | Rule |
|---|---|
| **R1** | **Python writes nothing.** Its database role holds `SELECT` on the chunk and embedding tables and nothing else. Postgres enforces this, not convention |
| **R2** | **Flyway owns the schema**, including the `vector` columns and their indexes. There is one migration tool |
| **R3** | **Python never authenticates and never authorizes.** It applies the `allowed_document_ids` it is handed. It never derives them, and never sees a JWT |
| **R4** | **Python is reachable only from Spring.** It binds `127.0.0.1`, never `0.0.0.0` |
| **R5** | **Document text crosses the boundary exactly once** — in the ingestion request. It never appears in a response body, and never in a log line on either side |

**R3 has a consequence that must be stated plainly: anyone who can reach this service can read any document in the database.** Authorization lives entirely in the caller. That is why R4 is a rule and not a deployment detail. A shared-secret header is the next increment; localhost-only is what stands today.

**R5 restates the Month 2 rule** that removed Logbook after it wrote passwords and JWTs to the console. Chunk IDs and scores cross the boundary; excerpts do not. Spring wrote the chunk rows, so it can hydrate any excerpt from its own database by ID.

---

## 2. Conventions

**Base URL.** `http://127.0.0.1:8000`, configured in Spring as `genai.base-url`.

**Auth.** None today (see R4). When the shared secret arrives it will be `X-Service-Token`, and a missing or wrong value will be `401` — which Spring treats as its own misconfiguration, never as a user error.

**Trace ID.** Spring sends its existing trace ID as **`X-Trace-Id`**. Python echoes it in every response body's `trace` object and on every log line, so one `grep` joins both services. If the header is absent Python generates one and says so in the log; absence is a Spring bug.

**Score direction — stated because it is the easiest thing here to get silently backwards.** pgvector's `<=>` operator returns **cosine distance**: `0` is identical, `2` is opposite, smaller is better. This contract never exposes distance. Every `score` in every response is **cosine similarity** (`1 - distance`): **higher is better**, `1.0` is identical. `min_score` is expressed in the same units.

**Errors.** FastAPI's envelope, with a code Spring can branch on:

```jsonc
{ "detail": { "code": "MODEL_NOT_READY", "message": "…", "trace_id": "…" } }
```

**Validation errors are Spring's bugs.** FastAPI answers a malformed request with `422`. Its default body shape is **normalised into the envelope above**, with `code: "MALFORMED_REQUEST"` and a `errors: [{field, error}]` list — Spring parses one shape on this boundary, not two. The frontend never reaches this service; Spring validated the user's input before calling it. A `422` here therefore means Spring sent something malformed — Spring logs it and returns a server error to the user. It is never translated into `400 VALIDATION_ERROR` and shown as though the user typed something wrong.

---

## 3. Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health/live` | The process is up. Never touches the models |
| GET | `/health/ready` | Both models are loaded and usable |
| POST | `/ingest` | Bytes in → chunks + vectors out. Writes nothing |
| POST | `/answer` | Question + allowed IDs → grounded answer + citations + trace |
| POST | `/retrieve` | Retrieval only, no LLM. Exists for evaluation, not for the product |
| GET | `/tools` | The tool schemas this service may propose. Read-only, executes nothing |

### `GET /health/live`

`200 {"status": "live"}` whenever the process is running. **Liveness must not check the models** — if it did, a restart under load would look dead and get killed in a loop.

### `GET /health/ready`

```jsonc
// 200 — both models loaded
{ "status": "ready", "embedding_model": "BAAI/bge-small-en-v1.5", "generation_model": "Qwen/Qwen2.5-0.5B-Instruct" }

// 503 — still loading, or a model failed to load
{ "detail": { "code": "MODEL_NOT_READY", "message": "generation model loading", "trace_id": "…" } }
```

Readiness reports honestly: it is `ready` only after both models have completed a real load. It never guesses from a flag set before loading started.

### `POST /ingest` — `multipart/form-data`

| Part | Type | Notes |
|---|---|---|
| `file` | binary | The document bytes. **Spring sends the bytes; Python never reads a filesystem** |
| `document_id` | UUID | For correlation only. Python does not look it up |
| `filename` | string | Used for extension-based extraction |
| `content_type` | string | As recorded at upload |

```jsonc
// 200
{
  "document_id": "…",
  "chunk_count": 37,
  "embedding_model": "BAAI/bge-small-en-v1.5",
  "embedding_model_revision": "<pinned commit sha>",
  "embedding_dim": 384,
  "chunks": [
    {
      "ordinal": 1,              // order within the document, 1-BASED
      "text": "…",               // Spring stores this; Python does not
      "token_count": 488,        // bge's tokenizer, never Qwen's. Ceiling 510 (see below)
      "char_start": 0,           // offsets index into the EXTRACTED text,
      "char_end": 2310,          // not the original file — for a PDF those differ entirely
      "section": "Approval",     // Markdown heading or spreadsheet sheet name. null if none
      "page": 7,                 // 1-based, PDFs only. null otherwise
      "embedding": [0.013, …]    // exactly 384 floats
    }
  ],
  "trace": { "extract_ms": 0, "chunk_ms": 0, "embed_ms": 0, "total_ms": 0 }
}
```

**Spring writes every chunk row in one transaction and only then sets `ready`.** A partially written document must never become retrievable — that is what the `ready` filter in `/answer` protects.

**This endpoint is CPU-bound** (PDF extraction, then embedding). It is a plain `def`, so FastAPI runs it in the threadpool. An `async def` here would block the event loop and take `/health/live` down with it.

### `POST /answer` — `application/json`

```jsonc
// request
{
  "question": "What is the parental leave policy?",
  "allowed_document_ids": ["…", "…"],  // REQUIRED, no default. MAY be empty
  "top_k": 5,
  "min_score": 0.35,
  "session_id": "…"                    // correlation only
}
```

**`allowed_document_ids` is required and has no default — and an empty list is legal.**

- Omitted → `422`, which is Spring's bug and should be loud.
- Empty → a normal state (a user with no ready documents). Returns zero chunks and `insufficient_context`.
- The filter is applied **unconditionally**. There is no `if allowed_ids:` branch, because that branch is the leak: with it, an empty list silently becomes a search across every user's documents. Validating non-empty would hide that branch without removing it.

Two tests hold this: a cross-user test (user A's IDs never return user B's chunks) and an **empty-list test** (zero rows, no exception). Spring computes the list as documents that are **owned *and* `ready`**.

```jsonc
// 200
{
  "outcome": "grounded",          // or "insufficient_context"
  "answer": "…",                  // "" when insufficient_context
  "citations": [
    { "chunk_id": "…", "document_id": "…", "ordinal": 12, "score": 0.71 }
  ],
  "trace": {
    "trace_id": "…",
    "retrieved": [                // EVERY retrieved chunk, including uncited ones
      { "rank": 1, "chunk_id": "…", "document_id": "…", "score": 0.71 }
    ],
    "top_k": 5,
    "min_score": 0.35,
    "candidates_before_threshold": 12,
    "allowed_document_count": 4,
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "embedding_model_revision": "…",
    "generation_model": "Qwen/Qwen2.5-0.5B-Instruct",
    "generation_model_revision": "…",
    "prompt_template_version": "qa-v1",
    "query_prefix_applied": true,
    "prompt_tokens": 1830,
    "completion_tokens": 96,
    "embed_ms": 41, "search_ms": 12, "generate_ms": 8400, "total_ms": 8453,
    "dropped_citations": []       // IDs the model cited that were not retrieved
  }
}
```

The trace exists so Spring can diagnose a bad answer **without opening Python's logs**:

- `retrieved` includes chunks that were *not* cited, because the common failure is "the right chunk ranked seventh" and a citations-only response cannot show it.
- `candidates_before_threshold` distinguishes *retrieved nothing* from *retrieved and filtered everything out*. Same symptom, different bug.
- `outcome` is an explicit enum, so Spring never sniffs the answer string.
- Split timings, because "slow" has three separate causes.
- `dropped_citations` is the honesty check — see §4.
- **No chunk text and no prompt appear anywhere in this object** (R5).

### Tool proposals — a field on `/answer`, not a second endpoint

Proposals come back **with the answer**:

```jsonc
"proposals": [
  {
    "label": "Create a tracking task",   // what the user reads on the approve/reject control
    "arguments": {
      "tool": "create-task",             // discriminator — matches Spring's ActionType
      "title": "Summarise the parental leave policy",   // max 255 = tasks.title VARCHAR(255)
      "priority": "high"                 // TaskPriority: low | medium | high
    }
  }
]
```

Spring turns that into the shape the frontend already receives — verified against the running service:

```jsonc
{ "id": "act-17c41ca8-…",                        // Spring mints it; becomes action_audit.action_id
  "type": "create-task",
  "label": "Create a tracking task",
  "payload": { "title": "…", "priority": "medium" } }
```

**No `proposal_id` is sent.** Spring's id is a *string* with an `act-` prefix, not a UUID, and it becomes the primary key of the audit row Spring owns. A second identity minted here would only be discarded.

Three tools, named **exactly** as Spring's `ActionType` enum names them — **hyphens, not underscores**:

| Tool | Spring payload it maps to |
|---|---|
| `create-task` | `CreateTaskPayload(title, priority)` |
| `summarize-document` | `SummarizePayload(documentId, documentName)` |
| `lookup-knowledge` | `LookupPayload(query)` |

The tracker writes these with underscores; the running system does not. `ActionType` writes these literal strings to `action_audit.type`, Jackson dispatches on them via `@JsonSubTypes`, and the frontend's `ActionProposal` union in `Type.ts` matches them. Emitting `create_task` here would need a translation layer whose only job is to undo a naming choice — a fifth hand-maintained copy of the contract.

**`summarize-document` carries a chunk ordinal *and* a resolved document id.** Spring's payload needs `documentId` *and* `documentName`, and this service cannot ask the **model** for either: a UUID costs 36 tokens and measurably stops the model citing at all, and the filename is not in its context. So the chain is: the model quotes a sentence → `resolve_quote` turns the quote into a 1-based ordinal over the chunks actually sent → **this service looks that ordinal up in its own retrieval result and fills in `document_id`** → Spring turns the id into a filename and re-checks ownership.

> **Corrected M3 D14b.** This paragraph previously stopped at "Spring maps the ordinal to the chunk row it wrote", and **nothing performed that mapping** — Spring received a `chunk_ordinal` it had no code to interpret, and `SummarizePayload` has no field for one. Jackson failed *closed* (`Unrecognized field "tool"`, loudly, rather than nulling), and it was unreachable because nothing proposed the tool, so it was latent rather than silent. It was still a specified step with no implementation. Two tests now pin it from both sides: `ToolRegistryConformanceTest` asserts `document_id` is published and `documentId` exists in Spring, and `ActionProposerTest` drives the translation against a real document row.

**Resolution happens in code on the Python side, translation on the Java side, and the split is not arbitrary.** Only this service knows which chunks it retrieved for this question; only Spring owns the `documents` table, so only Spring can supply a filename or perform an ownership check that means anything. Each half is done by the side holding the data.

**Why a field and not a call.** A separate `/propose` endpoint would re-run retrieval for the same question and split the trace across two requests, so Day 18 could no longer see the retrieval and the proposal that came from it in one object.

**Arguments are a discriminated union, not a free-form map.** `BACKLOG.md` item 2 records that Spring's outbound `Map<String, Object>` payload has no schema, so a typo in a key is invisible until the frontend misreads it. This boundary does not repeat that: an unknown tool name or a malformed argument is a validation error here, before it can reach Spring.

**Who decides *which* tool — M3 D14b.** This service does, in `app/intent.py`, from the **user's message only**. Never from retrieved text: a poisoned document cannot forge a tool call, because no chunk text reaches the router. The decision is a keyword trigger list **and** a logistic-regression classifier over the same bge vectors retrieval already computes, keywords asked first. Measured on the 27 held-out cases in `evaluation/tool_cases.json`: keywords alone 25/27, classifier alone 24/27, both together **26/27**, all three with **zero false positives**.

The rules used to live in Spring's `ChatSessionService` and were **moved, not copied** — along with a third reimplementation of them in `benchmarks/22`. Routing needs the encoder, which only this side has; translation needs the `documents` table, which only Spring has. The boundary now follows the data.

**Nothing here has executed.** Python proposes; Spring's existing governance flow decides, and writes an audit row either way — including rejections. `summarize_document`'s `document_id` is checked against `allowed_document_ids` in code, exactly like a citation; anything that fails is removed and recorded in `trace.dropped_proposals`. Fails closed.

### `GET /tools`

Publishes the registry — each tool's name, description, and JSON Schema for its arguments. Spring needs it to validate a proposal, and Day 14's evaluation set needs it to assert a tool is *not* proposed for an unrelated request. Without it both would keep their own copy of the tool list, which is the four-copies problem beginning again on its fifth copy.

**It had no consumer for five days.** A registry published so the tool list would stop being copied by hand, that nothing ever reads, prevents nothing. It now has three: `ToolRegistryConformanceTest` (Java), `tests/test_intent.py` (Python) and `Type.conformance.test.ts` (TypeScript) — so all three languages are asserted against one artefact rather than against each other's prose.

### `POST /retrieve` — `application/json`

Same request as `/answer`; returns the `retrieved` list and the trace, and **never calls the generation model**. This exists so Day 13's golden questions can test retrieval independently of generation, and so a bad answer can be bisected into "retrieval was wrong" or "generation was wrong". The product path does not call it.

---

## 4. Correctness does not depend on the model behaving well

A 0.5B model will sometimes invent a citation or answer from its own parameters. Every one of these decisions is made in **code**, not in the prompt:

| Decision | Where it is made |
|---|---|
| Whether there is enough context | In code, by comparing scores to `min_score` **before** the model is called. `insufficient_context` never reaches the LLM |
| Whether a citation is real | In code, by intersecting cited IDs with the retrieved set. Anything else is removed and recorded in `dropped_citations` |
| Whether a tool call runs | Never in Python. Proposals are returned; Spring's existing governance flow decides. Fails closed |
| Whether a proposal's arguments are valid | In code, by a discriminated union plus the same `allowed_document_ids` check used for citations. Rejects go to `trace.dropped_proposals` |

---

## 5. Failure mapping — what the user sees

Spring owns every user-facing outcome. Python never chooses one.

| Python does | Meaning | Spring does |
|---|---|---|
| Connection refused | Service isn't running | `503`, "AI unavailable". Not a stack trace |
| `503 MODEL_NOT_READY` | Models still loading | `503`, "AI still starting, try again shortly" |
| Exceeds timeout | CPU generation is slow | Abandon at the configured timeout. **Measured baseline below — a first cut is 45s, and it is a measurement, not a guess** |
| `422` | Spring sent a malformed request | Log as a Spring defect, return `500`. Never shown as a user input error |
| `500` | A bug in Python | Log, return `500`. If this was ingestion, set the document to `failed` |

### Measured on this hardware — Day 1

The service runs on an Intel Core i7-8750H. There is no GPU and no MPS, so these are the numbers the design has to live with:

| | Measured |
|---|---|
| `bge-small` embedding | **39 ms/chunk** (batch of 32), dim **384**, max sequence **512 tokens** |
| Qwen2.5-0.5B prefill | **~280 tokens/s** — linear across 66-3251 tokens (Day 3, 5 points). An earlier 205 came from one slow sample |
| Qwen2.5-0.5B decode | **4-8 tokens/s** — slows as context grows; this is the expensive half |
| Both models loaded at startup | ~2.7 s warm |

**A realistic answer is a 20–30 second request.** Extrapolating from the measured rates — not itself measured — `top_k = 5` at the full 512-token chunk size is roughly 2,700 prompt tokens ≈ **13 s of prefill**, plus 150 generated tokens ≈ **18 s of decode**.

Three things follow, and none of them are tuning:

1. **`top_k` costs less than first thought.** At ~280 tok/s a 510-token chunk adds ~1.8 s of prefill. Measured end to end on a real 16-page PDF, going from `top_k` 3 to 5 changed total latency by under a second. **Answer length is the real lever** — decode runs at 4-8 tok/s, so `max_new_tokens` bounds the worst case, not `top_k`.
2. **Spring's timeout cannot be a default.** Most HTTP client defaults are shorter than one successful answer.
3. **The synchronous answer path is now in question.** §8 already says ingestion cannot run inside the upload request. At 20–30 s, `POST /chat/message` is close to the same problem. This is a Day 8 decision and it needs a measurement on a real document first, not a guess made today.

---

## 6. Fixed constants

Changing any of these requires a migration, a re-embed, or both.

| Constant | Value | Consequence if changed |
|---|---|---|
| Embedding model | `BAAI/bge-small-en-v1.5` | New vector space — everything must be re-embedded |
| Vector dimension | **384** | Column type is fixed in the Day 5 migration |
| Max chunk size | **510 tokens, bge's tokenizer** | 512 minus the 2 special tokens the encoder adds. At 512 a chunk arrives as 514 and is **silently truncated** — the stored text would contain a tail its own embedding does not represent, so the passage could be cited yet never retrieved |
| Chunk overlap | **zero** | Overlap duplicates sentences; a duplicated sentence matches two chunks; an ambiguous quote is dropped. Overlap would destroy citations |
| Query prefix | `Represent this sentence for searching relevant passages: ` | Applied to **queries only**, never to documents. Applied in exactly one place |
| Generation model | `Qwen/Qwen2.5-0.5B-Instruct` | Prompt template and token budget both assume it |

**Model identity is stored per chunk row** (`embedding_model`, `embedding_model_revision`), and retrieval filters on the current model. Without that column, re-embedding with a different model leaves two vector spaces in one column and similarity search silently returns nonsense with no error anywhere. With it, old rows are simply invisible to the new query and a re-embed can run incrementally. Same shape as putting ownership in the `WHERE` clause: make the wrong rows unable to load.

---

## 7. Runbook, not migrations

Some setup is cluster-level and cannot live in Flyway:

- `CREATE EXTENSION vector;` — needs superuser. Runbook, once per database. V18 carries a comment saying where the extension came from.
- The read-only Python role and its `GRANT`s — a role creation in a migration would put a password in the repository. Runbook + environment variable.

---

## 8. Deliberately not decided today

| Open | Why not today |
|---|---|
| ~~Spring's timeout value~~ | **RESOLVED M3 D8: 90 s.** The 45 s first cut was below the measured worst case (Day 7: 30.8 s mean, **57.7 s worst**) and would have abandoned requests that were going to succeed. 90 s = worst case + headroom, in `app.genai.timeout` |
| Whether `POST /answer` can stay synchronous | **M3 D8: it does, and it should not.** 90 s synchronous is the honest ceiling, not a design. Spring holds no DB connection across the call (the turn is split into persist / call / persist), so the cost is a held HTTP thread rather than a deadlocked pool. Async + polling needs frontend work — Day 16 |
| Ingestion outside the request cycle | A large document exceeds any reasonable HTTP timeout. This is what makes `processing` a real status |
| What un-sticks a document stuck in `processing` | Needs a timestamp on the status transition before a sweeper can exist — so the *column* wants deciding by Day 5, even if the sweeper is built later |
| Token streaming | A streamed answer cannot carry a trailing `trace` object in the same shape. Known now, not designed for now |
| Shared secret between Spring and Python | R4 stands until then |

---

## 9. Revision history

| # | Day | Change |
|---|---|---|
| 14 | M3 D9 | **`Citation` gains `quote`** — the sentence FROM THE CHUNK that the model's quote resolved to. The model's own words are the lookup key and never the payload: it paraphrases (2 quotes in 3 failed to resolve on Day 7), so shipping its string would put generated prose on screen under a filename. Measured: a live citation went from the full 2,154-character chunk to a 53-character sentence, 2% of it. Empty when no single sentence stood out, and Spring falls back to the stored chunk text rather than showing nothing |
| 13 | M3 D8b | **`RetrievalRequest` gains `history: list[ConversationTurn]`** — `{role, content}`, oldest first, cap 50 as a sanity bound and truncated to `max_history_turns` in code. It DEFAULTS to empty, unlike `allowed_document_ids`, because absent and empty mean the same thing: a first turn has no history and that is not a caller defect. Spring sends it because Spring owns the `messages` table — `session_id` stays correlation-only and is still never looked up, so R1 holds and an answer stays reproducible from its own request. Used as a FALLBACK: the previous user turn is prepended only when the question alone matches nothing (measured — follow-ups score 0 alone and 5 with it, while standalone questions never reach the path, so there is no pollution). `trace` gains `history_turns_received` and `retried_with_history` |
| 12 | M3 D8 | **Spring now calls this service** — first consumer of the boundary. No schema change: the contract held on first contact, verified by POSTing Spring's own Jackson output to the running service (accepted, `grounded`, 1 citation, 19.7 s). Recorded here because the boundary is now load-bearing: `GenAiContractSerializationTest` asserts the five snake_case field names and that an empty `allowed_document_ids` serialises as `[]` rather than being omitted, since `extra="forbid"` makes one camelCase name a 422 on every request. The RESPONSE side tolerates unknown trace fields on purpose — that asymmetry is what let revisions 8 and 11 add trace fields without breaking a client |
| 11 | M3 D7 | **`AnswerTrace` gains `dropped_quotes: list[str]`.** Under qa-v2 the model never states an identifier, so `dropped_citations` (typed `list[UUID]`) can never populate — it is now documented as qa-v1-only. An unresolvable quote is the real drop signal: paraphrase, invention, or an ambiguous tie. Truncated to 60 characters so the trace cannot become a chunk-text side-channel. Also: `prompt_template_version` now defaults to **`qa-v2`**, resolved through a validated map — the default said `qa-v1`, the cite-by-number template Day 2 measured at right-chunk-cited 6/25 |
| 10 | M3 D7 | **`Citation.ordinal` REMOVED.** It had no consumer, verified against all three rather than assumed: the `citations` table has no ordinal column (`message_id, document_id, section, excerpt`), `CitationDto.java` is `id, documentId, documentName, section, excerpt`, and `Type.ts` matches. Spring hydrates excerpt and section from the `document_chunks` row `chunk_id` identifies, so an ordinal is redundant for lookup. Same rule that removed `description` from `CreateTaskArguments` on Day 2. Note that revision 9 corrected this field's floor one day before it was deleted — the consistency question was asked before the necessity question |
| 9 | M3 D6 | **`Chunk.ordinal` and `Citation.ordinal` corrected from `ge=0` / "0-based" to `ge=1` / "1-based".** They were the only place in the system claiming 0-based: chunking starts at 1, Postgres enforces `CHECK (ordinal >= 1)`, live rows run 1..24, `chunk_ordinal` already declared 1-based, and revision 7 says 1-based. Two defects — `ge=0` turned a caller mistake into a 500 from a CHECK constraint instead of a 422, and the published "0-based" description would have produced a silent off-by-one in Spring's client, since Java list access is 0-indexed. Caught while both fields were still behind `501`. Two tests hold it, one of which asserts against the live `/openapi.json` |
| 8 | M3 D6 | `RetrieveTrace` gains **`collapsed_duplicates`** (additive, defaults to `0`). Near-duplicate collapsing removes rows after ranking, so without this number a `top_k=5` that returns 2 chunks is indistinguishable from a corpus holding only 2 matches. Also: **`min_score` default raised `0.35` -> `0.60`** — 0.35 sat below the measured noise floor (unanswerable questions score up to 0.518), so `insufficient_context` could never fire. Request/response defaults are now read FROM `config`, not retyped in `schemas.py` |
| 1 | M3 D1 | Created. Boundary rules, endpoint shapes, error mapping. Nothing implemented — all endpoints return `501` |
| 2 | M3 D1 | `422` normalised into the standard envelope rather than left in FastAPI's default shape, so Spring parses one error format |
| 3 | M3 D1 | Added measured latency baseline. Timeout gets a number; whether `/answer` can stay synchronous becomes an open question |
| 7 | M3 D3 | `Chunk` gains `section` and `page` — feeding `CitationDto.section`, which already exists end to end and currently renders the literal `"Placeholder section"`. Chunk ceiling corrected from 512 to **510**: the encoder adds 2 special tokens, so 512 content tokens were silently truncated. `ordinal` is 1-based |
| 6 | M3 D2 | Verified against the **running** backend. Dropped `proposal_id` — Spring mints `act-<uuid>` as a string and it becomes `action_audit.action_id`. Replaced `rationale` with `label`, which is the field the frontend's `ActionProposal` union actually requires and renders |
| 5 | M3 D2 | Tool names aligned to Spring's `ActionType` (`create-task`, not `create_task`) after reading the enum, `@JsonSubTypes` and the frontend union. Removed `description` from `create-task` — no consumer exists in Spring, the tasks table or the UI. `summarize-document` now carries a chunk ordinal rather than a document id |
| 4 | M3 D1 | Declared the tool API: `proposals` as a field on `AnswerResponse`, `GET /tools` registry, arguments as a discriminated union. Shapes only — Day 10 designs them |
