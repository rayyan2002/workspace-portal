# Portfolio fork — context for the new chat

You are being handed two local folders that together form one working application. Your job
is to turn them into a **portfolio version** the owner can publish on their personal GitHub,
differentiated from the original, which lives on a company GitLab and must stay separate.

Read this whole file before touching anything. The system is heavily measured and most of
its constants were chosen against evidence; changing them casually will quietly make it
worse while the test suite stays green.

---

## 1. What the owner asked for, verbatim in intent

1. **Redesign the UI / theme** so it looks modern and professional.
2. **Swap the local models** for different HuggingFace models.
3. **Keep everything else structurally the same.**

Those two changes are what the owner wants as the differentiator. Do them well.

### Ownership — settled, do not reopen

The owner has confirmed: **this was their own solo training project, it contains nothing
confidential belonging to their employer, and the Gemini API key used during development
was their personal key.** The original lives on a company GitLab only because that is where
their training work was hosted.

So **do not run a confidentiality scrub and do not raise IP concerns.** Section 5 is about
*presentation* — making the repo read as a portfolio piece rather than a training diary —
and is entirely optional polish. Treat it as taste, not risk.

The one piece of ordinary hygiene that still applies regardless: **a personal API key is
still a secret.** `genai-service/.env` is correctly gitignored and must stay that way.

---

## 2. The system as it stands

Four processes. A React SPA, a Spring Boot API, a Python FastAPI GenAI service, and
Postgres with pgvector. Spring owns all writes; Python only reads.

| Part | Stack | Notes |
|---|---|---|
| Frontend | React 19.2, Vite 8, TypeScript 6, React Router 7, Vitest 4 | **Plain CSS, no Tailwind.** `lucide-react` icons |
| Backend | Spring Boot 4.0.7, Java 21, Maven, Flyway, JJWT | 20 migrations, `V1`–`V20` |
| GenAI | FastAPI, PyTorch 2.2.2, transformers 4.44.2, sentence-transformers 3.0.1 | Pinned hard — see §4 |
| Database | PostgreSQL 16.14 + pgvector | `document_chunks.embedding` is `vector(384)` |

**Scale:** 263 chunks across 14 documents, 20 documents total. 35 `.tsx` components,
14 stylesheets. Test suites: ~212 Spring, ~457 GenAI, ~37 frontend, plus a 24-test
opt-in golden suite.

### Architectural invariants — do not break these

- **Rule R1:** Python holds `SELECT` only on the chunk tables. Spring performs every write.
  This is documented in `INTEGRATION_CONTRACT.md` and enforced by convention. Keep it.
- **Vector-space isolation:** `document_chunks` carries `embedding_model` and
  `embedding_model_revision` columns *specifically* so that re-embedding with a different
  model cannot silently mix two incompatible vector spaces in one column. This design
  exists for exactly the change you are about to make — use it.
- **Models are revision-pinned**, not floating on `main`. Keep that discipline when you
  swap them; an unpinned model turns the test suite into a weather report.
- **`.gitignore` protects** `.env`, `*.env`, `uploads/`, `logs/`, `genai-service/logs/`,
  `uploads-orphans-quarantine/`. The Gemini API key lives in `genai-service/.env` and is
  correctly ignored. **Never commit any of these.** Verified clean today: no credential and
  no uploaded document is tracked in either repo.
- **The tool-calling flow is propose-never-perform:** the model proposes an action, a human
  approves or rejects, every decision is audited including rejections, and routing is
  derived from the user's message alone so a poisoned document cannot forge an action.
  `V20__one_decision_per_action.sql` makes a proposal decidable exactly once. This is the
  most interesting part of the project for a portfolio — do not simplify it away.

---

## 3. Task 1 — the UI redesign

This is the cheaper of the two tasks and has the higher visible payoff.

**The good news:** the styling is already tokenised. `src/index.css` defines **138 CSS
custom properties** — type scale, spacing scale, radii, and a full colour palette. There is
a working theme system in `src/context/ThemeContext.tsx` that supports **light / dark /
system**, applied as a `data-theme` attribute on `<html>`, with `system` deliberately
removing the attribute so the OS keeps driving the palette live.

**So a serious reskin is mostly re-tokenising `index.css`, not rewriting 35 components.**
Start there. Then adjust the 13 feature stylesheets in `src/styles/` (`chat.css`,
`dashboard.css`, `documents.css`, `document-detail.css`, `actions.css`, `layout.css`,
`login.css`, `management.css`, `settings.css`, `error-boundary.css`) plus `src/App.css`.

Rules for this work:

- **Preserve the three-state theme contract.** Define the full light palette on bare
  `:root`; override only what changes inside `@media (prefers-color-scheme: dark)` guarded
  by `:root:not([data-theme="light"])`; override again under `:root[data-theme="dark"]`.
  Never give a colour its only definition inside a media query — that breaks the toggle.
- **Do not introduce Tailwind or a component library** unless the owner asks. "Structure
  stays the same" includes the build. Plain CSS with good tokens is not a weakness to fix.
- **Keep the 37 frontend tests green.** Several assert on accessible names and roles, so
  renaming a button's label or swapping an element for a `<div>` will break them — which is
  the tests doing their job. Fix the markup, not the test.
- Check contrast in **both** themes. The current palette was not audited; this is a real
  chance to improve it rather than just restyle it.

---

## 4. Task 2 — swapping the models

**Read this entire section before choosing a model.** There is a hard platform ceiling and
there is measured evidence about specific models that will save you days.

### 4a. The platform ceiling is real and non-negotiable

The machine is an **Intel Mac (x86_64)**. PyTorch stopped publishing macOS x86_64 wheels
after **2.2.2**, so `requirements.txt` pins:

```
torch==2.2.2            # hard ceiling: no newer x86_64 macOS wheel exists
numpy==1.26.4           # torch 2.2.2 is built against the NumPy 1.x C API
transformers==4.44.2    # transformers 5.x needs torch>=2.5 and silently disables PyTorch
huggingface-hub==0.24.6 # transformers 4.44 cannot use the 1.x hub API
sentence-transformers==3.0.1
```

Unpinning any of these yields an install that **exits 0 and then cannot load a model**.

**Consequence: you must pick models that work with `transformers 4.44.2`.** Anything
needing a newer architecture — Qwen3, Gemma 3, Llama 3.3+ — will not load. Check the model
card's required transformers version *before* downloading several hundred megabytes.

Also note: `llama-cpp-python 0.3.36` is **installed in the venv but absent from
`requirements.txt`**. That is an undeclared dependency and a fresh clone will not reproduce
the environment. Either declare it or uninstall it — the owner has not decided. Flag it.

### 4b. The embedder — and the trap

Current: `BAAI/bge-small-en-v1.5`, **384 dims**, revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`.

**Pick another 384-dimension model and you need no database migration at all.** Change
`embedding_model` + `embedding_model_revision` in `genai-service/app/config.py`, re-embed
the 263 chunks, and the `embedding_model` column keeps the old vectors invisible to the new
queries. A 768-dim model instead requires a new Flyway migration changing
`document_chunks.embedding` to `vector(768)`, and Flyway is forward-only.

384-dim options compatible with `sentence-transformers 3.0.1`:

- `sentence-transformers/all-MiniLM-L6-v2` — different lab, very widely used, **no prefix**
- `thenlper/gte-small` — **no prefix**
- `intfloat/e5-small-v2` — needs `"query: "` and `"passage: "` prefixes

**The prefix matters and getting it wrong costs real accuracy.** `settings.query_prefix` is
currently bge's instruction string, `"Represent this sentence for searching relevant
passages: "`. If you move to MiniLM or gte you must **empty it**; for e5 you must set
`"query: "` *and* prefix passages with `"passage: "` at ingestion. A mismatched prefix looks
exactly like a bad model.

#### Already measured — do not repeat these

A benchmark (`genai-service/benchmarks/28_embedder_comparison.py`) compared candidates in
memory, each at its own swept floor, on this corpus:

| model | dims | encode | best floor | golden | reported | headroom | collision |
|---|---|---|---|---|---|---|---|
| `bge-small-en-v1.5` (current) | 384 | 4 ms | 0.59 | 9/9 | 5/5 | +0.0751 | **+0.0001** |
| `bge-base-en-v1.5` | 768 | 15 ms | 0.46 | 9/9 | 5/5 | +0.0585 | **−0.0349** |
| `e5-base-v2` | 768 | 11 ms | none exists | 8/9 | 5/5 | +0.0234 | −0.0099 |

**`bge-base-en-v1.5` is worse, not better.** It inverts the critical ordering: an off-topic
question (`"Follow up on finance"`, 0.5460) outranks a genuine one (`"what is university
policy"`, 0.5111). No threshold fixes a wrong ordering. `e5-base-v2` has **no floor at all**
that retrieves the golden set without leaking onto unanswerable questions.

Also already measured and rejected, with reasons recorded in the repo: a cross-encoder
reranker (worse and +2.1s), a trigram fallback (good and bad scores 0.011 apart — nothing
separates them), RRF hybrid search (noise 24→33), and smaller chunks (8/10 and 7/10 vs
9/10). Don't re-litigate these; read the benchmark headers.

#### The cost you must pay if you change the embedder

Every retrieval constant was swept against **bge-small's specific score distribution**.
A different model puts its scores somewhere else entirely, so these all become invalid:

```
default_min_score      0.55   the floor that produces "insufficient_context"
anchor_min_score       0.50   anchored expansion within the top-hit document
confident_score        0.60   upper bound of the margin-guard band
min_document_margin    0.02   document-margin guard
default_top_k          7
min_grounding_overlap  0.30
```

**Re-sweep them with `benchmarks/27_retrieval_floor.py` and `28_embedder_comparison.py`.**
If you skip this, retrieval will silently degrade while every test stays green, because the
golden suite is **opt-in** (see §6) and the default suite never exercises retrieval quality.

One finding that survives any model choice: headroom against off-topic questions that share
corpus vocabulary is **negative on all three models tested** (−0.069, −0.090, −0.036). No
absolute floor separates that class. The document-margin guard is the only mechanism that
does — keep it.

### 4c. The generation model

Current: `Qwen/Qwen2.5-0.5B-Instruct`, revision `7ae557604adf67be50417f59c2c2f167def9a775`.
`generation_max_new_tokens` is 1000.

**This swap is cheap** — no schema impact, no threshold re-sweep. It is the lower-risk half
of the model change, so if time is short, do this one properly and leave the embedder alone.

Latency reality on this Intel CPU: roughly **4–8 tok/s decode**, end-to-end about **87s**
for a full answer. Budget accordingly; a bigger model is proportionally slower.

Options that work with `transformers 4.44.2`:

- `HuggingFaceTB/SmolLM2-360M-Instruct` — different lab, Apache 2.0, **faster** than
  current. Best "differentiated and still demoable" pick.
- `HuggingFaceTB/SmolLM2-1.7B-Instruct` — noticeably better answers, roughly 3× slower.
- `Qwen/Qwen2.5-1.5B-Instruct` — **already in the local HF cache.** Better answers, but same
  family, so weaker as a differentiator.
- `meta-llama/Llama-3.2-1B-Instruct` — good, but **gated**: requires accepting a licence on
  HuggingFace and an auth token, which makes a fresh clone harder to reproduce.

Whatever you choose, **pin the revision** and re-run the golden suite to re-record what the
model actually scores. Do not copy forward accuracy claims measured on Qwen2.5-0.5B.

---

## 5. Presentation — optional polish, not risk mitigation

None of this is required. It is about making a visitor's first two minutes on the repo
land well. Pick what the owner wants; skip the rest.

**Worth doing, in rough order of payoff:**

1. **Replace the corpus and the evaluation fixtures.** This is the one item with a
   *technical* reason behind it too: `golden_questions.json`, `intent_train.json` and
   `tool_cases.json` must be regenerated anyway when the embedder changes (§4b), so do both
   at once. The current corpus is the owner's own training and assessment material —
   perfectly fine to own, but a stranger cloning the repo cannot evaluate a demo built on
   documents they have never seen. Swap in **public documents** (arXiv papers, government
   reports, open-source docs) so the golden questions are verifiable by anyone.
2. **Write a real `README.md`.** Right now the repo's front door is a training log. A good
   README showing the four-process architecture, the propose-never-perform action flow, and
   two or three of the measured findings from `benchmarks/` would do more for a portfolio
   than any amount of restyling. **This is probably the highest-value item on the list.**
3. **Retire the process documents.** `PROJECT_CONTEXT.md`, `genai-service/MONTH3_CONTEXT.md`,
   `genai-service/NOTES.md` and `BACKLOG.md` are working notes aimed at the owner and their
   mentor. They are not product documentation and they read as in-progress. Either drop them
   or fold the genuinely interesting parts into the README.
4. **Consider a fresh git history.** 73 commits titled `day#1 … day#19` read as a training
   diary rather than a project. A squashed initial commit plus a handful of meaningful ones
   presents better. **Purely a presentation choice** — and there is a real argument the other
   way: the commit messages in this repo are unusually good, they document *why* constants
   were chosen, and a reviewer who reads them will be impressed. If the owner is comfortable
   with the day-numbered framing, **keeping the history is a defensible and arguably better
   choice.** Ask; do not assume.
5. **Set a personal git author** on the new repo (`git config user.email` / `user.name`).
   A work address on a personal portfolio repo is just inconsistent, nothing more.

**Not worth doing:**

- Renaming the `com.bluestone.knowledge_assistant` package. It appears in 158 tracked files
  and the rename buys nothing — `bluestone` is a project namespace, not a liability.
- Scrubbing `Nisum` / `AeroTwin` strings from benchmark headers and fixtures. The owner has
  confirmed there is nothing confidential here. The benchmark write-ups are the strongest
  material in the repo; **do not rewrite their prose.** If the corpus is replaced per item 1
  the document names change naturally anyway.

**Ordinary hygiene before any push** — unrelated to the above, do this regardless:

```bash
git ls-files | grep -iE "\.env|uploads/|logs/"   # expect only public/.env
```

`public/.env` in the frontend is fine; it holds `VITE_API_BASE_URL` and `VITE_USE_MOCK` and
no secret. What must never be committed is `genai-service/.env`, which holds a real
(personal) Gemini API key. It is already covered by `.env` and `*.env` rules — verified.

---

## 6. Traps that will bite you

- **The golden suite does not run by default.** `pyproject.toml` sets
  `addopts = "-q -m 'not golden and not routing'"`. So "457 tests pass" says **nothing**
  about retrieval or answer quality. After any model change, run it explicitly:
  ```bash
  cd genai-service && ./.venv/bin/python -m pytest -m golden -q
  ```
  It takes ~25 minutes (real generation, 24 tests) and needs Postgres plus both models.
- **There is a known failing golden test**, and it is not a bug in the code:
  `test_answers_stay_grounded_in_the_documents[setup-part-count]`. The model answers `7` to
  a counting question whose answer is `5`; the grounding guard correctly withholds a wrong
  answer; the test asserts *"a legitimate answer was withheld"* about an answer that was not
  legitimate. The deeper issue is that `grounding_overlap` on a bare-number answer can only
  return 1.0 or 0.0 depending on whether that digit happens to appear in the source text —
  it measures digit presence, not provenance. The golden file carries
  `expect_answer_contains: ["5"]` which **no test asserts**. Expect to fix the test, and
  consider asserting answer content; a different generation model will change this outcome.
- **Spelling correction is correctly gated — do not "fix" it.** `app/spelling.py` rewrites
  words absent from the corpus vocabulary, which in isolation produces alarming output
  (`runway → ranjay`, `aero → zero`). But `retrieval.py:320` only invokes it when the first
  search returned nothing, and keeps the result only if the corrected query then retrieves
  something. Measured on 48 real questions: 39 never invoke it, and **3 corrections were
  applied, all of them genuine typos correctly fixed**. The "keep it only if it retrieves"
  rule is doing the job a dictionary would do, and doing it better. Adding a word list is
  the wrong fix and adds a dependency for nothing.
- **Postgres needs `CREATE EXTENSION vector;` run manually** by a superuser before
  migrations. It is deliberately not in a migration — see the header of
  `V18__create_document_chunks.sql`. On this machine pgvector had to be built from source
  because the Homebrew bottle targets PG 17/18 and this cluster is 16.14.
- **The owner runs the dev servers themselves.** Do not occupy their ports.
- **Vectors are stored normalised**, so cosine similarity is the dot product and retrieval
  uses `<#>`. That is an obligation, not an optimisation — a column mixing normalised and
  un-normalised rows ranks nonsensically and nothing reports an error.

---

## 7. House rules the owner expects

- **Ask before every commit or push. Permission never carries over.** Report what would be
  committed, then wait.
- **Design before code. Measure, never assert.** This repo's whole character is that
  constants have evidence behind them. If you change a threshold, show the sweep.
- **Say what you skipped.** Do not report a gate as green when part of it did not run —
  that is exactly how the golden regression above went unnoticed.
- **There is a training tracker `.xlsx` in the corpus. It is reference only — never write
  to it.** It leaves naturally if the corpus is replaced (§5 item 1).

---

## 8. Suggested order of work

The owner's two actual requirements are items 1 and 2. Everything after is optional.

1. **UI redesign** (§3). Highest visible payoff, fully independent of everything else, and
   mostly re-tokenising `index.css` rather than rewriting components. Start here.
2. **Swap the generation model** (§4c). Cheap, no threshold re-sweep, no migration. Pin the
   revision and re-run the golden suite to record what the new model actually scores —
   do not carry forward numbers measured on Qwen2.5-0.5B.
3. Write a real **`README.md`** (§5 item 2) — the best return per hour in this whole list.
4. Replace the **corpus and evaluation fixtures** (§5 item 1) if the embedder is changing
   or if the owner wants a demo a stranger can verify.
5. Only if genuinely wanted: swap the **embedder** (§4b), and pay the full threshold
   re-sweep cost. Read the measured table first — the obvious "upgrade" is a downgrade.
6. Ask the owner about **git history** (§5 item 4). There is a good case for keeping it.
7. Decide the undeclared **`llama-cpp-python`** dependency either way (§4a).
8. Fix or re-scope the known failing **golden test** (§6).
