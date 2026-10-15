# Month 3, Days 1–4 — Review Map

**What this is:** a map of what exists, where it lives, and the evidence behind each decision.
It is *not* a script. Every "why" below is a decision with a measurement attached — if you
cannot say the measurement, go and look at the code before the review rather than reciting
the line.

Run `./.venv/bin/python -m pytest tests` first. 78 tests, ruff clean, pyright clean.

**Every statistic below is reproducible.** The scripts that produced them are in
`benchmarks/`, with a table in `benchmarks/README.md` saying what each proves and how long it
takes. When he asks "where does that number come from", the answer is a command, not a claim:

```bash
cd genai-service
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/02_chunk_corpus.py
```

Postgres must be running — several read the live database and the real `uploads/` directory
rather than fixtures. Numbers will not match to the decimal (this is a laptop, it throttles);
the *ranking* and order of magnitude should.

---

## The one-minute version

A FastAPI service that will do the RAG work, with **every endpoint declared and returning
`501`**. Four days built the pipeline *up to* the vector: extract → chunk → embed. Nothing
in Spring calls it yet; the tracker puts that on Day 8.

| Day | Deliverable | State |
|---|---|---|
| 1 | Service skeleton + integration contract | Done |
| 2 | Prompt templates + parser | Done |
| 3 | Chunking pipeline | Done — 177 chunks from 21 real documents |
| 4 | Embedding pipeline | Done — 177 vectors, all unit norm |
| 5 | pgvector migration | Done — V18 applied, 177 chunks stored |

---

## "Show me the schema" — Day 5

`src/main/resources/db/migration/V18__create_document_chunks.sql` in the **backend** repo.

```bash
psql -d knowledge_assistant -c "\d document_chunks"
```

```bash
psql -d knowledge_assistant -c "SELECT count(*), count(DISTINCT document_id) FROM document_chunks;"
```

**Four decisions to be ready for:**

**`ON DELETE CASCADE`, where `citations.document_id` is `RESTRICT`.** A chunk is *derived* —
regenerable from the document, and embedding is bit-for-bit deterministic (Day 4), so
regeneration is exact. A citation is a **record of what the assistant said** and must not
vanish because a file was tidied. Same column shape, opposite answer.

**No `token_count <= 510` CHECK**, even though 510 is a real invariant. It belongs to the
embedding *model*, not the schema, and `embedding_model` is recorded per row. A CHECK would
need migrating every time the model changed — and migrations are forward-only.

**`CREATE EXTENSION` is not in the migration.** Superuser only; a migration demanding one
either fails for the app role or forces a privileged credential into the repo. V18 fails
loudly on a fresh database without it, which is intended.

**No vector index**, and this is a measured decision:

```
    rows  exact ms  ivfflat ms   hnsw ms
    1000       0.7         0.8       0.7
   10000       4.2         0.8       1.1
   50000      31.6         0.9       2.0
```

Exact search is linear; indexes stay near 1 ms. **Crossover ~10,000 rows — 56x this corpus**,
and at 1,000 rows both indexes were *slower*. An index arrives in its own migration when the
corpus approaches five figures.

**Say this before he asks:** the recall column in that benchmark is **not trustworthy**, and
the script prints so itself. It scores ID-overlap, which on clustered synthetic data measures
tie-breaking; and pgvector defaults `ivfflat.probes = 1`, which alone predicts the numbers.
Neither was separated, because the decision did not depend on it.

## "pgvector setup" was not a one-liner — Day 5

```bash
brew install pgvector    # succeeds, and installs NOTHING usable
```

The bottle builds for postgresql@**17 and 18**; this cluster is **16.14**. `CREATE EXTENSION`
fails and nothing warns you the install targeted another major version. Fixed by a source
build with `PG_CONFIG` pointed at the right Postgres — that flag is the entire point. On
macOS the artifact is `vector.dylib`, not `.so`. It is now in `README.md` **including the
failing command, marked**.

*This is a good answer to any question about Day 20 deployment prep: works on a laptop,
fails elsewhere, and previously lived only in shell history.*

---

## "Why FastAPI when the tracker says Flask?"

`INTEGRATION_CONTRACT.md` §0.

Primary reason is **familiarity** — the web framework is the thinnest layer of this service,
so the month's learning budget goes to RAG rather than to an unfamiliar HTTP layer.
Secondary: FastAPI derives its OpenAPI spec from the same Pydantic models that validate
requests, so the spec cannot disagree with the server.

**Say the caveat yourself before he asks:** the spec does not prevent drift. Spring's client
is hand-written until it is generated from the spec or checked against it in a test. Logged
as `BACKLOG.md` item **3a**.

---

## "Where does the boundary sit, and why?"

`INTEGRATION_CONTRACT.md` §1 — five rules.

**Python reads, Spring owns.** Flyway keeps sole schema ownership, Spring performs every
write and all authorization, Python's role holds `SELECT` on two tables.

*Why not let Python own the database:* the ownership rule would exist twice in two languages,
and its failure mode is silent — another user's text inside an answer, with nothing erroring.

*Why not keep retrieval in Spring:* chunk size, top-k and thresholds are the month's
experiments; they belong next to the embedding code.

**The consequence, stated rather than discovered:** anyone who can reach this service can
read any document. That is why it binds `127.0.0.1` — a rule, not a deployment detail.

---

## "Show me the liveness/readiness split"

- `app/routers/health.py:12` — `live()`, never touches the models
- `app/routers/health.py:27` — `ready()`, **raises** rather than returns
- `app/models_registry.py:54` — `start_loading()`, a background thread
- `app/models_registry.py:60` — `_fail_remaining()`

They answer different questions: *should you kill this process* versus *should you send it
traffic*. Loading runs in a background thread because a blocking load means the socket never
opens, so `/health/live` is connection-refused for the whole startup — **indistinguishable
from a crashed process**, which is how a restart loop begins.

**Two defects worth showing him, both found by tests:**

1. `ready()` declared `response_model=ReadyResponse`, so the 503 body was validated against
   the *success* shape and the endpoint answered **500**. It raises now.
2. `import torch` sat outside both `try` blocks, so an error there killed the loader thread
   with both states still `LOADING` — readiness reported "still loading" **forever**. A dead
   service reported as a slow one. `_fail_remaining()` in a `finally` fixes it for every
   escape route, including an early `return` added later.

---

## "Why does every endpoint return 501?"

`app/errors.py:85` — `not_implemented()`.

A stub returning plausible data looks finished and proves nothing. The *request* model is
live, so a malformed call already returns a correct 422 today. Month 2 recorded what an
endpoint with no consumer does: it drifts.

---

## "Walk me through the citation design"

This is the part with the most evidence behind it, and the part that changed most.

**Day 2 measured three output formats**, same model, chunks, question and seeds:

| | A: JSON + UUIDs | B: prose + `[n]` | C: JSON + numbers |
|---|---|---|---|
| Output usable | 5/10 | 10/10 | 10/10 |
| Citation recoverable | 0/10 | 10/10 | 10/10 |

Asked to echo a UUID the model **stopped citing entirely** — a UUID costs 36 tokens against
3 for a number.

**Then cite-by-number was overturned the same afternoon.** Five questions × five runs:

```
answer came from the right chunk : 23/25  (92%)
cited exactly the right chunk    :  6/25  (24%)
```

It reads the right passage and guesses the label — and not with a correctable bias: chunk
`[1]` was cited 15 times across five unrelated questions.

**So `qa-v2` asks for the SENTENCE and resolves it in code.** `app/prompts/parsing.py:246`
(`resolve_quote`) and `:279` (`parse_quoted_answer`). The model never states a chunk number,
so it cannot state a wrong one.

**Result:** misattribution 13/25 → 2/25, right chunk cited 11/25 → 20/25.

**The subtle point he may probe:** Day 1's `dropped_citations` guard rejects numbers *outside*
the retrieved set. Every wrong citation here was *inside* it. **A guard against invalid
citations is structurally blind to inaccurate ones** — which is why the fix had to change
what the model is asked for, not add another check.

---

## "Why is there no example in the prompts?"

`app/prompts/templates.py` module docstring, rule 2, and the test that enforces it.

| Instruction | Cited the right chunk |
|---|---|
| `...like [2]` | **0/10** — emitted `[2]` nine times |
| `...like [N]` | 3/10 — and **silent 5/10** |
| `...in square brackets` | 10/10 |

A placeholder was **worse than a specimen**. And the generalisation is the part worth saying:
**anything you show the model is an example, including the data.** `qa-v2` renders context
*unlabelled* (`app/prompts/templates.py:85`, `render_context(numbered=False)`) because the
`[1] [2] [3]` chunk labels taught it to answer a request for a verbatim quote with `"[5]"` —
8 times in 25.

---

## "How do you handle the model not following the schema?"

**Parse leniently, validate strictly.** `app/prompts/parsing.py`.

Asked for `"cites": [1, 2]` it returned `[{"number": 1, "context": "[1]"}]` in **10 runs out
of 10** — valid JSON, improvised schema. A strict `isinstance(c, int)` filter reads that as
zero citations *with total confidence*, which is exactly the bug that produced a wrong result
during the experiment.

Number extraction reads only keys that *name* a chunk, never text-bearing ones like `value` —
the model echoes chunk prose there, and chunk prose contains numbers like "12 weeks".

---

## "Show me the chunker"

- `app/ingestion/extract.py:59` — `extract()`, dispatch on **content then extension**
- `app/ingestion/chunk.py:51` — `chunk_document()`
- `app/ingestion/chunk.py:81` — `_pack()`, sentence-aware greedy packing

**Three decisions, none of them preference:**

1. **Sentence-aware packing.** Day 2 made this a *dependency*: citations resolve a quoted
   sentence to a chunk, so a chunk ending mid-sentence produces quotes matching nothing.
2. **Zero overlap**, against convention. Overlap duplicates sentences → a duplicated sentence
   matches two chunks → `resolve_quote` drops ambiguous matches. **Overlap would destroy
   citations.**
3. **Chunks never cross a segment boundary** — one PDF page, one heading, one sheet. That is
   what makes `page` and `section` *true* rather than approximately true.

**Dispatch is never on MIME type:** three live documents are `application/octet-stream` and
are actually a `.md` and `.xlsx`.

**Supported formats come from `DocumentService`'s allow-list, not the corpus.** There is no
`.docx` uploaded anywhere and `.docx` is accepted — building from the corpus would have left
a hole the first upload fell into.

---

## "What went wrong in chunking?"

Two silent failures, and both are good answers to *"what did you learn"*:

1. **The offsets lied.** Chunk text is stripped; `char_start` was left pointing at the
   discarded leading whitespace. Unit tests passed because hand-written fixtures have tidy
   whitespace — **extracted PDF text does not**. Every excerpt in the UI is a slice at these
   offsets, so two characters of drift is a quote starting mid-word.
2. **The 512 ceiling was wrong by two.** bge adds `[CLS]`/`[SEP]` itself, so 512 content
   tokens arrive as 514 and are truncated **silently**. Demonstrated: a 1,141-token text and
   its 510-token prefix embed to `cosine = 1.000000` — the tail contributes *nothing*. Such a
   chunk is **citable but unretrievable**. The corpus maxed at exactly 510, so nothing was
   harmed; that was luck, not design.

---

## "Why is the embedding batch size 1?"

`app/ingestion/embed.py:70`.

Measured twice, in both directions, because the first sweep confounded batch size with
time-into-the-run on a CPU that throttles:

```
batch      1     4     8    16    32    64
ms/chunk  99   154   146   177   188   191     (sweep 1 -> 64)
ms/chunk 104   135   143   172   205   226     (sweep 64 -> 1)
```

**Why: padding, from MIXED chunk lengths.** Controlled test — same chunk count, two
arrangements (`benchmarks/10_batch_vs_heterogeneity.py`):

| arrangement | real tokens | batch64/batch1 |
|---|---|---|
| homogeneous, all ~480 | 30,720 | **0.89** — batching wins |
| mixed, half 480 half ~10 | 15,584 | **3.72** — batching loses |

The mixed set has **half the real work** and batch 64 took nearly twice as long. Short chunks
pad up to the longest member of their batch.

**This is the strongest thing to walk him through**, because it took three attempts. Two
explanations were wrong and are still in the repo: core saturation (killed by `07`) and
sequence length (killed by re-running `06`). I had also dismissed padding early because
sentence-transformers length-sorts — *that dismissal was the real error*, since sorting
cannot help when the batch is the whole input.

**The decision never moved.** `DEFAULT_BATCH_SIZE = 1` rested on a measurement from the
start; only the explanation kept failing. That distinction is worth making explicitly.

---

## "What about retries?"

`app/ingestion/embed.py:149` — `_encode_with_backoff()`.

**The concept does not transfer.** "Retry handling" presumes an API: network faults, rate
limits, 5xx. A local encode fails *deterministically*, so retrying a bad input fails again,
slower. The one transient failure is memory pressure, and the answer is to **halve** the
batch — the only "try again" that changes the thing that failed. A test asserts
`attempts == [16, 8, 4]`.

Same shape as Flask→FastAPI: the tracker's vocabulary assumes a hosted model.

---

## Questions he is likely to ask that you should NOT bluff

**"Does it actually answer questions well?"** — *No, and it cannot yet.* Retrieval does not
exist (Day 6). Compound questions fail **0/5** — the model answers the first clause and
stops, proven not to be chunking, retrieval or prompting. Quality is unmeasured until Day 13.

**"How long does an answer take?"** — 15.5–18.7 s measured on a real 16-page PDF, worst case
38–52 s at the 200-token cap.

**"Do the actions work?"** — Partly. `create-task` 2/4, `summarize-document` 4/4,
`lookup-knowledge` 1/4, **false positives 0/8**. And Spring only *executes* `create-task`;
the other two return placeholder strings while reporting `completed`.

**"What is wrong with the corpus?"** — It is duplicated **2.72x by chunk** (177 chunks,
65 distinct texts) and **2.10x by document** (21 documents, 10 distinct bodies), and one text
appears **five times** — so `top_k=5` really can be a single passage repeated under five
filenames. *An earlier draft of this map said "~4x"; that was an impression from counting
filenames, not a measurement. Corrected by query.* Day 6 needs near-duplicate collapsing; Day 13 cannot measure
precision until the duplicates go.

---

## The thing worth volunteering

Day 3 began by discovering that most of what had been assumed about this codebase came from
a summary document rather than the codebase. Reading the code and then **running the system**
corrected six things, three of which would have shipped as bugs — including tool names
(`create-task`, hyphens, not `create_task`), which were the only outlier in the entire
system, and a `proposal_id` that Spring would have discarded.

Contract revisions **5, 6 and 7** record them. Three were visible only by running the service.

**The generalisable lesson: a summary of a system is not the system.**
