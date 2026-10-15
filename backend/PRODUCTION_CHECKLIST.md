# Production configuration checklist

Month 3, Day 17. Three processes, three configuration systems, one deployment.

**Every "what happens if it is wrong" column in this document was measured or is held by a
test.** Nothing here is inferred from reading code. That distinction is the point: a checklist
assembled from what the code *looks like* it does is a document that agrees with itself and
with nothing else, and this project has been caught by that often enough to stop doing it.

Where something is genuinely unmeasured it says **not measured** rather than guessing.

---

## 0. Before you deploy anything — the three that matter

| | |
|---|---|
| **`JWT_SECRET`** | The default is **committed to this repository**. Anyone with read access can mint a token for any user. The application refuses to start with it unless **every** active profile is a development one — held by `JwtSecretValidatorTest`. |
| **`SPRING_PROFILES_ACTIVE`** | **Must be set, and this is the fix for the worst thing Day 17 found.** It previously was not required: no profile was treated as development, so a deployment that simply forgot it started on the public signing key and warned. The protection was real and its trigger was undocumented. Absence of a profile is now **refused**. |
| **`GENAI_GEMINI_API_KEY`** | Only set it if you intend document text to leave the machine. Choosing the cloud backend sends retrieved chunks to Google. Absent, the service runs local-only. |
| **Network exposure** | The GenAI service has **no authentication** and trusts the `allowed_document_ids` it is handed. Anyone who can reach it can read any document. It binds `127.0.0.1` for that reason — do not change that without putting something in front of it. |

---

## 1. Spring Boot — `src/main/resources/application.properties`

### Database

| Variable | Default | Required in production | If wrong |
| --- | --- | --- | --- |
| `DB_URL` | `jdbc:postgresql://localhost:5432/knowledge_assistant` | **yes** | *Not measured.* Expected to fail at startup on the connection pool, but the failure mode was not reproduced. |
| `DB_USERNAME` | `rayyanayub` | **yes** | A developer's local username is the default. It will not exist in production. |
| `DB_PASSWORD` | *(empty)* | **yes** | Empty works against a locally trusted socket and will not elsewhere. |

> **The default username is a person's laptop account.** It is the kind of default that works
> everywhere it is written and nowhere it is deployed.

### Security

| Variable | Default | Required | What happens — **test-backed** |
| --- | --- | --- | --- |
| `JWT_SECRET` | the checked-in dev key | **yes** | Default + any non-development profile → **refuses to start**, naming `JWT_SECRET` *and* telling a developer that `SPRING_PROFILES_ACTIVE=dev` is what makes it go. Default + `dev`/`test`/`local` → warns and continues. Default + **no profile** → **refuses** (changed D17). Shorter than 32 bytes → **refuses everywhere**, including dev: HMAC-SHA256 cannot sign with less. Missing → refuses. |
| `SPRING_PROFILES_ACTIVE` | *(none)* | **yes** | Unset → the application refuses to start while the default key is in use. Set it to `prod` for a deployment, `dev` locally. |
| `JWT_ISSUER` | `knowledge-assistant` | no | — |
| `JWT_ACCESS_TTL` | `15m` | no | — |
| `JWT_REFRESH_TTL` | `7d` | no | — |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | **yes** | *Not measured.* Must list the real frontend origin or the browser blocks every request. |
| `TRUST_PROXY_HEADERS` | `false` | only behind a proxy | Controls whether `X-Forwarded-For` is believed when keying rate limits. **A client can set that header.** Enabling it on a directly-exposed server lets an attacker defeat every IP-keyed limit below by varying one string. |

> **Two rules were inverted on Day 17, both after this document put them side by side.**
>
> 1. **No profile is no longer development.** It was, which made the entire protection
>    conditional on a variable nothing instructed anyone to set.
> 2. **Every active profile must be a development one.** The old check asked whether *any*
>    was, so `prod,local` warned and continued — and adding a profile is an ordinary thing to
>    do, not something that should switch a security control off.
>
> The cost is local: `./mvnw spring-boot:run` with nothing set now refuses, and says which
> variable fixes it. `.claude/launch.json` sets `dev`, so the normal path is unaffected.

### GenAI client — `app.genai.*`

**Measured before Day 17: eight deliberately bad values, eight accepted.** All eight now
refuse startup, held by `GenAiPropertiesValidationTest`.

| Property | Env | Default | If wrong — **measured** |
| --- | --- | --- | --- |
| `app.genai.base-url` | `GENAI_BASE_URL` | `http://127.0.0.1:8000` | Empty, blank, `not-a-url`, or a non-HTTP scheme → **refuses to start**. The message names `GENAI_BASE_URL`, not just the property key, because that is what an operator actually sets. |
| `app.genai.timeout` | — | `420s` | **Seven minutes, and not a defensible synchronous timeout** — it is the measured consequence of a 1000-token output cap on a CPU decoding at 2.7 tok/s (Day 19). Raised from 150s with the cap, because a 1000-token answer needs ~374s of decode and would otherwise time out while working. The fix is the asynchronous answer path, or the cloud backend. `0s` or negative → **refuses**. |
| `app.genai.connect-timeout` | — | `2s` | `0s` or negative → **refuses**. |
| `app.genai.top-k` | — | `7` | **Sent on every request, so it overrides the Python default rather than agreeing with it** — raised 5 → 7 on Day 18b (BACKLOG 24) and changing only the Python side would have done nothing. `0` or negative → **refuses**. Previously accepted, and the GenAI service rejects `top_k < 1` with a 422 — so a Spring misconfiguration surfaced as *"the AI service refused the request"*, pointing at the wrong service. |
| `app.genai.min-score` | — | `0.55` | **Sent on every request, so it overrides the Python default** — lowered 0.60 → 0.55 on Day 19 (BACKLOG 28) and changing only the Python side would have done nothing. Outside `[-1, 1]` → **refuses**. Cosine similarity cannot exceed 1, so a floor of `5.0` can never be cleared and every question returns `insufficient_context` **while the service looks healthy**. |
| `app.genai.history-turns` | — | `6` | Negative → **refuses**. |

### Rate limits — `app.security.rate-limit.*`

Added Day 17. **The defaults are honest guesses, not measurements** — there is no production
traffic to tune against, and a precise-looking number would imply otherwise.

| Property | Env | Default | Keyed by | Why |
| --- | --- | --- | --- | --- |
| `login-per-minute` | `RATE_LIMIT_LOGIN_PER_MINUTE` | `10` | IP | Before this, password guessing was bounded only by network speed. Reduces an online brute force from one address to ~14,400 guesses a day. |
| `register-per-hour` | `RATE_LIMIT_REGISTER_PER_HOUR` | `5` | IP | Creates a row. |
| `password-reset-per-hour` | `RATE_LIMIT_PASSWORD_RESET_PER_HOUR` | `5` | IP | Sends mail to an address the caller chooses. |
| `upload-per-minute` | `RATE_LIMIT_UPLOAD_PER_MINUTE` | `20` | **user** | Since Day 16 an upload runs extraction, chunking and embedding synchronously — the resource protected is the embedding model, not disk. |
| `enabled` | `RATE_LIMIT_ENABLED` | `true` | — | `false` logs a **WARN** at startup. Off in the test profile only. |

**Known limitations, stated rather than discovered:**

- **In-memory and per-process.** Two instances behind a load balancer each allow the full
  quota; a restart forgets every counter.
- **Login is keyed by IP**, because there is no authenticated user yet. A shared NAT can
  exhaust a colleague's allowance. Keying on the submitted email would be worse — an attacker
  varies it freely and sidesteps the limit entirely.
- **Fixed window, not a token bucket**, so a burst of up to 2× the limit is possible across a
  window boundary. Irrelevant for brute-force protection; the average rate still holds.

### Storage and mail

| Variable | Default | Note |
| --- | --- | --- |
| `UPLOADS_DIR` | `uploads` | Relative to the working directory. Must be writable and must **persist** — the bytes are re-read if a document is ever re-ingested. *Unwritable behaviour not measured.* |
| `MAIL_ENABLED` | *(empty)* | With no credentials the reset email is logged instead of sent. `POST /api/auth/forgot-password` returns **202 either way**, deliberately, so it cannot be used to discover which addresses have accounts — **the log is the only place a send failure appears.** |
| `MAIL_HOST` / `MAIL_PORT` / `MAIL_USERNAME` / `MAIL_PASSWORD` | Gmail SMTP / `587` / placeholder / empty | — |

---

## 2. GenAI service — `genai-service/.env`, prefix `GENAI_`

**Measured before Day 17: of eleven deliberately bad values, TEN were accepted silently.**
They now refuse startup with a message naming the environment variable.

| Variable | Default | If wrong — **measured** |
| --- | --- | --- |
| `GENAI_OVERFETCH_FACTOR` | `4` | `0` was accepted and made **every query retrieve nothing**, with no error anywhere. Now `>= 1`. |
| `GENAI_DEFAULT_MIN_SCORE` | `0.55` | **The number that decides whether `insufficient_context` is reachable.** Measured ceiling for unanswerable questions is 0.5175, so a floor at or below that makes the service answer what the corpus cannot — invisibly. 0.50 and 0.51 leak; 0.52 and above do not. See `benchmarks/27_retrieval_floor.py`. `5.0` was accepted and put the floor above the maximum possible cosine similarity — every question `insufficient_context`, service apparently healthy. Now bounded to `[-1, 1]`. |
| `GENAI_DEFAULT_GENERATION_BACKEND` | `local` | `gpt4` was accepted, and the service then **silently served local**. Now restricted to `local`/`gemini`. |
| `GENAI_PROMPT_TEMPLATE_VERSION` | `qa-v2` | One template for both backends. An unknown version was accepted and failed per-request. Now checked against the templates that exist. |
| `GENAI_DB_NAME` | `knowledge_assistant` | Empty was accepted and failed at the **first user's question**. Now rejected at startup. |
| `GENAI_EMBEDDING_MODEL` / `GENAI_GENERATION_MODEL` / `GENAI_GEMINI_MODEL` | pinned | Whitespace is stripped — a trailing space inside `.env` quotes once became `%20` in a request path and answered 400. Blank now rejected. |
| `GENAI_DEFAULT_TOP_K` | `7` | Bounded `1..50`, matching the published contract. Only used when Spring does not send `top_k`, which in practice it always does. |
| `GENAI_ANCHOR_MIN_SCORE` | `0.50` | The floor for chunks from the document the top hit already identified (BACKLOG 24). Bounded `[-1, 1]`, and **must stay below `GENAI_DEFAULT_MIN_SCORE`** or the band is empty and anchored expansion is silently disabled. It is below the unanswerable ceiling by design: expansion cannot run unless something already cleared the real floor, which an unanswerable question never does. |
| `GENAI_MAX_DOCUMENTS` | `1` | How many documents may contribute to one answer. **This is what makes the 0.55 floor affordable** — it removed all 29 off-document chunks the lower floor introduced, at full recall and fewer tokens than the 0.60 setting it replaced. `2` or `3` if a cross-document question appears (BACKLOG 29); `0` disables the limit. |
| `GENAI_CONFIDENT_SCORE` | `0.60` | Above this a match stands on its own. Below it, `GENAI_MIN_DOCUMENT_MARGIN` also applies. |
| `GENAI_MIN_DOCUMENT_MARGIN` | `0.02` | **How far the best document must lead the second, for a marginal match to be answered at all.** This is what makes a 0.55 floor safe: "what is university policy" (0.5926) and "Follow up on finance" (0.5925) are one ten-thousandth apart on chunk score, and only the document margin separates them — 0.0428 against 0.0047. `0` disables the guard. |
| `GENAI_MIN_GROUNDING_OVERLAP` | `0.30` | Bounded `[0, 1]`. |
| `GENAI_EMBEDDING_DIM` | `384` | Must match the `vector(384)` column. A mismatch fails the model load with both numbers named. |
| `GENAI_GEMINI_API_KEY` | *(none)* | Held as `SecretStr`, never logged. Absent → requesting `gemini` returns **503 naming the reason** rather than quietly serving local. |
| `GENAI_LOAD_MODELS` | `true` | `false` only for tests. `/health/ready` then reports *"model loading was never started"* rather than "loading", so a misconfigured service never looks like a slow one. |
| `GENAI_VERBOSE_TRACE` | `false` | Prints the full retrieval/generation report to stderr. A demo aid — **not** a log level, so it stays off during an incident. |
| `GENAI_LOG_PROMPTS` | `false` | **The one setting that writes document text to disk.** On, the full prompt goes to `logs/prompts.log` and into every `answers.jsonl` record, so both become a partial copy of the corpus — rotated, and readable by anyone who can read logs. A WARN is logged at startup while it is on. Held by `test_log_redaction.py` in both states. **Must be `false` in production.** |

> **Editing `.env` is not enough while `--reload` is running.** The uvicorn reloader watches
> `.py` files only, so a corrected `GENAI_*` value stays dormant and the running process keeps
> serving the old one — which has already caused one measurement to describe the previous
> configuration. **Restart the service after any `.env` change.** `Settings` is built once at
> import, so this is true with or without the reloader.

**Model revisions are pinned and must stay pinned.** Every stored vector records the model and
revision that produced it. Changing one leaves two vector *spaces* in one column, and
similarity search then returns nonsense with no error.

---

## 3. Frontend — Vite

| Variable | Default | Note |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://localhost:8080` | Baked in **at build time**, not read at runtime. A production bundle built with the default points at localhost on the user's own machine. *Not measured.* |
| `VITE_USE_MOCK` | unset | Switches to MSW handlers. Must be unset in production, or the app serves fabricated data that looks entirely real. |

---

## 4. Startup order

1. **PostgreSQL** with the `vector` extension.
2. **GenAI service** — two models, ~45s. `/health/ready` returns **503** until both are loaded;
   an upload during that window ends `failed` with *"The AI service is still starting up"*,
   which is correct and not what you want on a first run.
3. **Spring Boot** — Flyway migrates on start.
4. **Frontend.**

```bash
curl -s http://127.0.0.1:8000/health/ready    # wait for 200 before uploading
```

---

## 4. Logging — where it goes and what is in it

Added M3 D18. Before it, **both services logged to the console only**: every diagnostic lived
in terminal scrollback and died with the window.

| File | Written by | Contents |
| --- | --- | --- |
| `logs/backend.log` | Spring | human-readable, same layout as the console |
| `genai-service/logs/app.log` | GenAI | human-readable |
| `genai-service/logs/answers.jsonl` | GenAI | **one JSON object per answer**, nothing else |

| Variable | Default | Note |
| --- | --- | --- |
| `LOG_FILE` | `logs/backend.log` | Spring. Rotates at 10MB, 7 days, **200MB total cap** — `max-history` bounds the number of files, not the bytes. |
| `GENAI_LOG_DIR` | `logs` | Relative to the GenAI service's working directory. |
| `GENAI_LOG_TO_FILE` | `true` | `false` keeps console only. **Both test profiles set this off**, so a test run cannot write into the application's own operational data. |
| `GENAI_LOG_MAX_BYTES` / `GENAI_LOG_BACKUP_COUNT` | 10MB / 5 | Rotation. |

**One trace id spans both services** since D18 — `GenAiClient` now forwards `X-Trace-Id`,
which it never did despite the GenAI service logging a warning about it on every request. So:

```bash
grep <trace-id> logs/backend.log genai-service/logs/app.log
```

**`answers.jsonl` is safe to keep, and that is tested.** It carries scores, chunk ids,
timings, token counts, parse path, citation source and the routing decision — and **no
question, no answer, no chunk text, no filename**. The question appears only as a 12-character
hash and a length. `tests/test_log_redaction.py` asserts this against the real path, and the
assertion was itself verified by deliberately leaking the question and watching it fail.

> **The logs are not aggregated and not shipped anywhere.** Two rotating files per host and
> `jq`. Disk is bounded by rotation; nothing alerts.

---

## 4a. Running the tests

`.github/workflows/ci.yml` runs all three suites on push and pull request — Python (no
database), Spring (Postgres with pgvector), and the frontend's contract tests.

**Before Day 17 nothing ran them but a person typing `./mvnw test`.** That is why
`JwtSecretValidator` went two months untested: there was no mechanism that could have
reported it. The workflow is **not yet verified against a real runner** — no remote is
configured, so the first push will be the first execution of it.

---

## 5. What this checklist does **not** cover

- **DB, CORS, uploads-dir and frontend failure modes are not measured.** They are marked as
  such above. Everything in the GenAI and `app.genai.*` tables is.
- **No secret manager.** Secrets come from the environment and `.env`. `.env` is gitignored;
  nothing enforces that it stays so.
- **No TLS, no reverse proxy, no container.** `TRUST_PROXY_HEADERS` anticipates a proxy that
  does not exist yet.
- **Rate limits are per-process.** See the limitations above.
- **No runtime config endpoint.** Settings are visible in the GenAI service's `trace` and in
  Spring's startup log, and nowhere else.
