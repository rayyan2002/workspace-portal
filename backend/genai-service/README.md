# GenAI Service

The Month 3 AI service for the AI Workplace Knowledge Assistant: retrieval, generation,
citations, and the tool router. Called **only** by the Spring Boot backend — never by the
browser. The boundary is specified in [`../INTEGRATION_CONTRACT.md`](../INTEGRATION_CONTRACT.md).

**Setup, configuration and the system-wide runbook live in [`../README.md`](../README.md)**,
which is the document to read first and is duplicated in the frontend repository. This file
covers what is specific to this service.

---

## This machine constrains the stack

Not a preference — measured on Day 1, and still true:

| | |
|---|---|
| CPU | Intel Core i7-8750H (x86_64). **No Apple Silicon, so no MPS** |
| Python | **3.11 only** (Homebrew). `python3` on PATH is 3.14 and has **no torch wheel at all** |
| torch | **2.2.2 is a hard ceiling** — PyTorch stopped publishing macOS x86_64 wheels after it |

Everything in `requirements.txt` is pinned to what torch 2.2.2 can work with. An unpinned
`pip install` **exits 0 and produces a broken environment**: numpy 2.x breaks torch's C API,
and transformers 5.x disables PyTorch outright ("PyTorch >= 2.5 is required but found 2.2.2").
Read the comments in `requirements.txt` before changing a version.

## Setup

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

First run downloads ~1.2GB of weights to `~/.cache/huggingface`.

## Run

```bash
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**`--host 127.0.0.1`, never `0.0.0.0`.** This service has no authentication and trusts the
`allowed_document_ids` it is given, so anyone who can reach it can read any document. That
is rule R4 in the contract, not a deployment detail.

- `/docs` — the contract, generated from the same models that validate requests
- `/health/live` — up. Never touches the models
- `/health/ready` — `503` until both models have genuinely loaded, and it names the one it
  is still waiting on

> **`uvicorn --reload` watches `.py` files only.** An edited `GENAI_*` value in `.env` stays
> dormant while the old one keeps serving. Restart after any configuration change.

## What it does

| Endpoint | |
|---|---|
| `POST /answer` | question + allowed document ids → answer, citations, proposals, full trace |
| `POST /retrieve` | the same search without generation — the quickest way to ask *"what would the model have seen?"* |
| `POST /ingest` | document bytes → chunks and embeddings, returned to Spring to write |
| `GET /tools` | the tool registry Spring renders proposals from |

**Two rules hold the boundary**, and both are deliberate asymmetries:

- **This service never writes to the chunk tables.** It holds `SELECT` only; every write is
  Spring's. A read-only service cannot corrupt the corpus it reads.
- **It validates strictly and Spring reads leniently.** Pydantic rejects an unknown field
  with a `422`; Jackson ignores one. Spring sending something unexpected should fail loudly
  and at once, while a field added here must not break a backend not yet redeployed.

### Citations are resolved from quotes, never from numbers

The model is never asked for an identifier of any kind. Day 2 measured the alternative:
asked for a chunk **number** it answered from the right passage 23/25 times while citing the
right one 6/25, with chunk `[1]` cited 15 times across five unrelated questions. It reads the
right text and guesses the label.

So the model quotes a **sentence**, and `prompts/parsing.py` matches that sentence back to a
chunk. The model cannot state a wrong number because it never states one, and an ambiguous
quote is dropped rather than guessed.

### Retrieval has two modes

| `retrieval_mode` | |
|---|---|
| `similarity` | the normal path: chunks ranked by closeness to the question |
| `document_summary` | the request routed to `summarize-document`, so the chunks are the **opening of the best-matching document, in document order** |

The second exists because a question about a document *as a whole* gives similarity nothing
to rank by — every chunk is equally "about" the paper. Measured on an 81-chunk paper, the
abstract ranks **34th** for *"what is this paper about"*. Choosing the document by similarity
works (0.632–0.726 across four phrasings); only choosing *within* it needed position.

The similarity path also uses **anchored expansion**: the top hit names a document, and
chunks from that document are admitted down to a lower floor. It cannot fire unless something
already cleared the real floor, so it cannot manufacture an answer out of nothing.

## Test

```bash
./.venv/bin/python -m pytest
```

**424 tests**, no model loading and no database (`GENAI_LOAD_MODELS=false`, the connection
faked), so the suite runs in seconds. That is the point: a test suite needing 1.2 GB of
weights is one nobody runs.

```bash
./.venv/bin/python -m ruff check app tests benchmarks
npx pyright app tests
```

**Both are separate gates and neither is implied by the tests.** A green `pytest` and a green
`ruff` together once hid 84 type errors, because neither of them type-checks anything.

### The golden set — 24 tests, deselected by default

```bash
PYTHONPATH=$PWD ./.venv/bin/python -m pytest -m golden
```

Known questions with known sources, asserted against the **local** backend so it is
deterministic, free, and immune to a cloud quota. It loads both models and queries the real
corpus, so it takes minutes — hence `addopts = -m 'not golden'`.

It asserts retrieval reaches the right **chunk**, not merely the right document. A
document-level assertion passed for the entire life of a bug in which the right file was
returned and none of the right text.

### `benchmarks/` is the evidence, not a demo

Every default in `config.py` — the score floor, `top_k`, the template, greedy decoding, the
grounding threshold — was set by a script in there. **Read the relevant one before changing a
threshold**; several record fixes that were measured and rejected, which is the part that
stops them being retried. `26_retrieval_gate.py` is the clearest example: three plausible
repairs, all measured worse than the one that shipped.

## Measured on this hardware

Day 1 figures, re-measured over 23 logged answers on the real corpus:

| | |
|---|---|
| bge-small embed | 39 ms/chunk (batch of 32), dim **384**, max seq **512 tokens** |
| Query embedding | ~19 ms |
| pgvector search | ~18–41 ms |
| Qwen2.5-0.5B prefill | ~280 tokens/s |
| Qwen2.5-0.5B decode | **2.7 tokens/s** median, range 0.4–4.8 |

| Backend | Median answer | Range |
|---|---|---|
| **local** (Qwen2.5-0.5B) | **55.5 s** | 32–144 s |
| **gemini** (hosted) | **8.2 s** | 0.1–23 s |

**Retrieval is never the slow part** — embedding and search together are under 60 ms, and
generation is everything else. Two corrections to earlier figures, both recorded rather than
quietly replaced:

- Prefill was first reported as 205 tok/s. That came from dividing **one** 993-token
  measurement that happened to land slow, and was ~40% pessimistic.
- A full local answer was first described as 20–30 seconds. It is now a median of 55.5 s,
  because `top_k` rose from 5 to 7 and the prompt grew with it. Shorter prompts are still
  better; the saving is just smaller than first claimed.
- **Decode was reported as 8.2 tok/s and is 2.7.** That figure came from Day 1, on short
  prompts, and was carried forward unchecked into this file on Day 19 — including by the
  clean-room pass, which verified the *commands* and not the *numbers*. Measured over 22
  real answers in `logs/answers.jsonl` it is a median of 2.7 tok/s, falling as the prompt
  grows. It matters because it sets the output cap: 1000 tokens at 2.7 tok/s is **374
  seconds**, which is why `app.genai.timeout` is 420s.

This shapes Spring's timeout, `top_k`, and whether the answer path can be synchronous at
all. See the contract, §8.

## Logs

Two rotating files under `logs/`, both capped at 10 MB:

| | |
|---|---|
| `app.log` | the ordinary application log |
| `answers.jsonl` | **one JSON object per answer** — scores, counts, timings, token counts, model identity, which code path ran, what the router decided |
| `prompts.log` | the full prompt per request, **only when `GENAI_LOG_PROMPTS=true`** |

`answers.jsonl` contains **no document text, no question, no answer and no quote**. The
question appears only as a length and a 12-character hash; chunks appear only as UUIDs.
That is what makes it safe to keep and to ship, and `tests/test_log_redaction.py` asserts it
against the real path rather than trusting it.

**`GENAI_LOG_PROMPTS=true` is the one setting that changes this**, and it was added on
request. With it on there is a third file, `logs/prompts.log`, holding the full prompt for
each request — and the same prompt is added to every `answers.jsonl` record as a `prompt`
object. The prompt contains the retrieved chunks, so both files then hold document text and
the paragraph above is no longer true of that installation.

It is off by default, a WARN is logged at startup while it is on, and the redaction test
covers **both** states: nothing leaks with it off, and with it on the prompt reaches only
those two places. Turn it on to debug a prompt; do not leave it on where logs are shipped.

Each record names a **`verdict`** and, where something is off, the **`suspect`** stage —
`retrieval`, `generation` or `parsing` — because a bad answer looks identical from the
outside whatever caused it. The vocabulary is tabulated in [`../README.md`](../README.md) §9.

> **`grounded` means the answer's words came from the documents. It does not mean the answer
> is correct.** This measures provenance, not truth: a model that reads the right passage and
> states the opposite of it scores perfectly here, and Qwen-0.5B has done exactly that.

`GENAI_VERBOSE_TRACE=true` additionally prints a full human-readable report to stderr. It
writes document text, so it is a demo aid and **not** a log level — it stays off during an
incident, which is precisely when someone would otherwise turn it up.

## Layout

```
app/
  config.py            every setting, validated AT STARTUP; model ids pinned by revision
  schemas.py           every request/response shape — this is the contract
  models_registry.py   loads both models once, in a background thread
  retrieval.py         pgvector search, duplicate collapsing, the floor, anchored expansion
  answering.py         prompt -> model -> answer + citations + the grounding guard
  generation.py        the local model and the Gemini client
  prompts/
    templates.py       versioned prompts; every rule in them was measured
    parsing.py         a model reply -> an answer and resolved citations
  ingestion/           extract (pdf, docx, xlsx, csv, md), chunk, embed
  intent.py            which tool, if any, a message is asking for
  safety.py            quarantines instruction-like text found inside documents
  observability.py     the JSON answer trace, and the verdict above
  errors.py            one error envelope, including FastAPI's 422
  trace.py             X-Trace-Id propagation from Spring
  verbose.py           the stderr report
  routers/             health, ingest, answer + retrieve, tools
evaluation/            the golden set, the router's training and held-out sets
benchmarks/            the measurements every default is set from
tests/
```

`NOTES.md` carries the day-by-day findings; `MONTH3_CONTEXT.md` is the working context for
continuing the month.
