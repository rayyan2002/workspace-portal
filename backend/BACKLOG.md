# Backlog — verdicts, not a list

Every deferral accumulated across Month 2, each with a decision rather than sitting undifferentiated. Four verdicts: **DEBT** (should be fixed, isn't), **MONTH 3** (correctly waiting on AI work), **BY DESIGN** (deliberate, fine indefinitely), **DONE**.

---

## DEBT — real, unfixed, should be scheduled

### 1. ~~Eight failing frontend tests~~ — **RESOLVED, and my diagnosis here was wrong**

I originally wrote that the pages had changed so much the tests asserted a UI that no longer exists, and offered "fix or delete" as the verdict. That is two decisions dressed as one, and the premise was false. Every one of the nine tests asserts behaviour that still exists — including the governance approval flow, the most valuable test in the suite.

Two causes, neither of them the tests:

**Mechanical, and nothing to do with shapes.** MSW registers handlers on *relative* paths; `apiFetch` — added Day 15 — prefixes `VITE_API_BASE_URL` unless `VITE_USE_MOCK` is set. Every request therefore went to an absolute URL and matched no handler. The suite broke the day `apiFetch` landed, and nobody saw it because there was no `npm test` script until Day 16.

**Contract drift, again.** The mocks returned Month-1 shapes. Fixing `mocks/handlers.ts` was not enough — `DocumentsPage.test.tsx` carries its own inline overrides, which had drifted separately.

That is **four hand-maintained copies of the contract**: backend DTOs, `Type.ts`, `mocks/handlers.ts`, and per-test overrides. All four diverged independently. **Verdict: FIXED** — 9/9 passing.

### 2. Action proposal payload is `Map<String, Object>`
`ActionProposalDto.payload` is an untyped map on the way out, while the inbound `ActionRequest.payload` is a properly sealed discriminated type. The response side has no schema, so a typo in a key is invisible until the frontend misreads it.

**M3 D14b — still an untyped map, now a TESTED one.** The map is no longer *forwarded*: `ActionProposer` rebuilds every field of every proposal from scratch, and `ActionProposerTest.theServicesArgumentMapNeverReachesTheBrowser` asserts that a key invented upstream cannot ride along into it. `Type.conformance.test.ts` then asserts the keys the frontend reads are exactly the ones Spring's payload records declare. A typo now fails a build on one side or the other rather than being "invisible until the frontend misreads it".

**Verdict: DEBT, downgraded.** The type safety is still weaker than the request side's sealed union, and the reason is now deliberate rather than incidental — see `GenAiProposal`: a Jackson polymorphic union would throw while deserialising the whole response, so one malformed proposal would cost the user their *answer*. Failing closed has to happen per-proposal, which the map plus a validating translator achieves and a typed union does not.

### 3. The frontend's types are a hand-written copy of the backend's DTOs
Every contract break this month was found by a human clicking — the login shape, the paged envelope, the admin endpoint's shape. Backend tests assert the backend's view; frontend tests assert mocks; nothing asserts they agree.

Item 1 sharpened this considerably. The contract exists in **four** hand-maintained copies — backend DTOs, `Type.ts`, `mocks/handlers.ts`, per-test overrides — and all four drifted independently this month. More copies means more places to forget, and the count is the problem.

So the fix is not a new test category. A test hitting the real backend from the frontend suite reintroduces every database-isolation problem solved on Day 14. **The tractable fix is to stop hand-maintaining the copies**: springdoc already publishes an OpenAPI spec at `/v3/api-docs`, so `Type.ts` can be *generated* from it. Shape drift then becomes a compile error rather than a discovery, and the mocks can be typed against the generated types so they cannot drift silently either.

**Verdict: PARTIALLY FIXED — M3 D14b.** Not by generating `Type.ts`, which remains the better long-term answer, but by giving the browser boundary the thing it actually lacked: *a test*.

`src/test/resources/action-contract.json` is a committed snapshot of the action vocabulary — types, decisions, statuses, priorities, payload fields, result shapes. `ActionContractSnapshotTest` holds **Spring** to it by reflecting over the enums and payload records; a verbatim copy at `src/test/action-contract.json` in the frontend, plus `src/Type.conformance.test.ts`, holds **`Type.ts`** to the same bytes. Neither side can edit the snapshot to make itself pass: changing it to suit the frontend fails the Java test, and changing Spring fails the Java test until the snapshot is regenerated, at which point the frontend fails until `Type.ts` follows. Verified by deliberately renaming a field in each direction and watching the opposite side go red.

`Type.ts` also stopped hand-repeating its literals. Four inline copies of the same three string unions became `as const` arrays with the unions derived from them — which is what made a runtime test possible at all, since TypeScript types erase — plus a compile-time assertion that ties the runtime key map back to the payload interfaces in both directions. `npm run build` runs `tsc`, so a payload key removed from one and not the other is a build error naming the tool.

**It found two real defects before it had guarded anything:**

1. `ActionService` returned an approved summary as a **bare string** while `ActionCard.tsx` has always rendered `result.summary` — `undefined` against a string, so the feature rendered an empty card with no error in any log. Notably `mocks/handlers.ts` had the shape *right*; the frontend was built against a correct mock and the real backend quietly differed, which is precisely the gap no single-language test can see.
2. `Type.ts` exported `ActionStatus = 'pending' | 'approved' | 'rejected'`, matching **neither** of Spring's two enums — `'pending'` existed nowhere in the system. It had zero consumers, which is the only reason nothing was visibly broken, and is how an unchecked copy rots: the wrong part is the part nobody uses, until somebody uses it.

**Remaining DEBT:** `mocks/handlers.ts` and the per-test inline overrides are still hand-maintained, and generation from `/v3/api-docs` is still the structural fix for everything beyond the action vocabulary. The count of copies is lower and two of them now fail loudly; it is not zero.

### 5. ~~`DocumentStatus.processing` and `failed` are never produced~~ — **RESOLVED, M3 D16**
Both values existed in the enum with nothing able to emit them. `processing` became reachable on Day 11 and `failed` on Day 16, when ingestion was finally wired to upload: a document that the GenAI service cannot extract, or that yields zero chunks, now ends `failed` rather than silently `ready`-with-no-chunks. A 201 is still returned, because the upload itself succeeded — the bytes are stored and the row is committed — and a 5xx would be a lie about that while leaving the user with no document at all.

### 15. Test uploads were written into the application's own upload directory — *added M3 D16*
`app.uploads.dir` had no test override and there was no `application-test.properties`, so every upload test wrote fixture bytes into the directory the running application serves documents from, and nothing cleaned up. Measured: **11,553 files, of which 11,531 matched no `documents` row** — 2,480 created in a single day by repeated `./mvnw test` runs, almost all 29–33 bytes of fixture payload.

Nothing broke, which is why it survived two months: the document list is built from the `documents` table, so a file with no row is never read. It is a disk leak that grows with the suite.

**Verdict: FIXED for new runs** — the `test` profile writes to `${java.io.tmpdir}`, verified by running the suite and watching the directory not grow. **DEBT remaining:** the 11,531 existing orphans are still on disk. Deleting them is irreversible and is the user's call, not a cleanup to do quietly.

### 16. The grounding guard is inflated by function words — *added M3 D16*
`grounding_overlap` counts the fraction of the answer's words that appear in the retrieved chunks, and common English words count. Measured: *"Paris is the capital of France and the weather there is generally mild"* scores **0.364** against three unrelated chunks — above the 0.30 floor — entirely on `is`, `the`, `of`, `and`, `there`.

Found because a test of mine asserted that sentence would be withheld and it was not; the code was right and my example was wrong. The guard still does its job on the case it was built for (fluent text with no source at all), but its threshold is doing less work than 0.30 suggests.

**Verdict: DEBT.** The fix is content-word filtering or a stopword list, and the threshold is a measured value — moving it needs `benchmarks/18` re-run, not a guess.

### 17. Repeated PDF page headers are duplicated into every chunk — *added M3 D16*
Five of the eight chunks extracted from `University_Admission_Prospectus_2027.pdf` begin with the same header block (`NORTHFIELD UNIVERSITY OF SCIENCE & TECHNOLOGY / Admissions Prospectus 2027`). A header repeated on every page becomes noise in every chunk: it costs tokens against the 510 ceiling, and it dilutes the per-chunk discrimination `resolve_quote` depends on to pick ONE source.

**Verdict: DEBT.** Detecting a line repeated across most pages and dropping it is a contained change in `extract.py`, but it alters every stored chunk, so it needs re-ingestion and a retrieval measurement rather than a quiet edit.

### 18. Tests write into the application's own operational data — *added M3 D18*
**Three instances in three days, which makes it a pattern rather than three accidents.**

1. **D16** — 11,531 orphaned files in `uploads/`, because the test profile had no
   `app.uploads.dir` override. 2,480 created in a single day by repeated `./mvnw test` runs.
2. **D18** — 16 of the first 54 lines of the real `genai-service/logs/answers.jsonl` were a
   traceback from `test_log_redaction.py`'s deliberate "the trace blew up" case, which
   corrupted the JSON Lines format for every line-by-line consumer.
3. **D18, avoided** — Spring file logging was added with the test-profile override written
   at the same time rather than after being bitten.

The common cause: a test inherits a production path because nothing says otherwise, and
nothing fails when it does. **Verdict: FIXED in all three places** (`uploads`, `GENAI_LOG_TO_FILE`,
`logging.file.name`), **DEBT remaining** — there is no general guard. A fourth
output path added tomorrow will default to the production location again, and the only thing
standing between that and a repeat is somebody remembering. A test that asserts the test
profile writes nothing under the repository root would close it.

### 19. Type checking is not in any automated gate — *added M3 D18*
`pyright` is configured in `pyproject.toml` and read by Pylance, so errors are visible in the
editor and **in nothing else**. `ruff` and `pytest` both pass while 84 type errors exist —
measured, on Day 18, across files written over Days 15–18. The project had already recorded
being bitten by this once (*"benchmarks was omitted here and its type errors went unseen for
a day"*) and it recurred.

**Verdict: DEBT.** The fix is one step in `.github/workflows/ci.yml`; it was not added on Day
18 because that workflow is itself still unverified against a real runner, and adding an
unverified step to an unverified workflow proves nothing.

### 20. ~~The retrieval floor admits noise at 14 documents~~ — **SUPERSEDED, M3 D19**
Measured in `benchmarks/25_score_distribution.py`. On a live question, four of five retrieved
chunks were unrelated to the question — a training tracker, an aviation deck, a marking
spreadsheet — each clearing the 0.60 floor by about two hundredths, costing 2,325 prompt
tokens and 45.9 seconds.

    floor   median admitted   questions returning nothing
    0.60                  4                             0
    0.62                  2                             0
    0.64                  1                             1

**0.62 halves the admitted chunks at no cost on the golden set.** Deliberately NOT changed on
a logging day — and **BACKLOG 24 now measures the same floor as too HIGH on another question**,
so raising it would be trading one failure mode for the other. Read the two together. The likelier root cause is BACKLOG 17 — a repeated PDF page header in five of
eight prospectus chunks inflates every score it appears in, so the threshold may be the wrong
lever entirely. **Verdict: DEBT, with the measurement already done.**

### 21. The grounding guard cannot see a short answer — *added M3 D18b*
`grounding_overlap` is the fraction of the ANSWER's words found in the retrieved chunks, so
the denominator is chosen by the model. A one-word answer that appears anywhere in the corpus
scores a perfect 1.000.

Measured, against three chunks about a university prospectus:

    answer        overlap   what it should be
    "Germany"       1.000   wrong, and invented
    "42"            1.000   wrong, and invented
    "France"        0.000   also wrong — but scored correctly
    a real quote    0.667   right, and scored WORSE than both inventions

The guard is strongest on the case it was built for — fluent, sourceless prose — and blind in
inverse proportion to answer length, which is the opposite of what a threshold implies.

**This is LATENT, not live, and the distinction was nearly misreported.** All three
unanswerable golden questions retrieve **zero chunks** and return `insufficient_context`
before the model is called at all, so the hallucination path is unreachable through real
retrieval; the measurement above forced chunks into the prompt directly. It bites only when
retrieval succeeds AND the model answers briefly and wrongly.

**Verdict: DEBT.** Same root cause as BACKLOG 16, opposite direction — 16 is the numerator
inflated by function words, this is the denominator being too small to mean anything. Both
want content-word scoring, and the floor is a measured value, so they should be fixed and
re-measured together rather than separately.

### 22. An empty answer is reported as `grounded` — *added M3 D18b*
`Outcome` has two values, `grounded` and `insufficient_context`, and they describe
RETRIEVAL. When retrieval succeeds and the model then declines, the response is
`outcome: grounded, answer: "", citations: []` — and the verbose trace prints **"VERDICT:
built from the retrieved text"** over an empty string, with `grounding overlap 0.000`.

That is how the Day-18b Gemini bug stayed invisible for two sessions. Every signal said the
request succeeded; the only evidence of a problem was the frontend's fallback copy, *"I found
relevant passages in your documents but couldn't put together an answer"*, which is the UI
inferring a failure the API declined to report.

**Verdict: DEBT.** A third outcome value is the right answer, and it crosses three
codebases — the Pydantic enum, Spring's DTO, and the frontend's hand-written copy of it
(BACKLOG 3).

A `qa-v3` prompt that declined less readily was built and measured as a workaround, then
**removed once BACKLOG 24 was fixed**: with retrieval returning the right chunk, qa-v2
answers the question, and a second template would have been a permanent branch in the prompt
path justified by a defect that no longer exists. The decline rule is not the problem — a
model that declines when the context genuinely does not answer is behaving correctly. The
problem is that this service reports that decision as a success.

### 23. `uvicorn --reload` does not watch `.env` — *added M3 D18b*
Eighth instance this month of acting on a process that no longer matched its source. `.env`
was corrected, the service was not restarted, and the old value stayed live — so the next
measurement described the previous configuration. The reloader watches `.py` only, which
makes the failure specific to exactly the files an operator edits when fixing configuration.

Worth knowing rather than fixing: `--reload-include .env` exists, but a settings object
built at import time and bound into `app.config.settings` would need the restart regardless.
**Verdict: documented, not debt.** Recorded in `PRODUCTION_CHECKLIST.md` §1 so it is written
down somewhere an operator reads.


### 24. ~~A single global similarity floor cannot serve both failure modes~~ — **RESOLVED, M3 D18b**
**The defect behind the Gemini "failure", and it was in retrieval, not in the model or the
prompt.** Reported as *"Gemini worked on qa-v2 before and crashes now"*; neither half was
true. `generation.py` had not been touched in five days, and the model had not crashed — it
declined, correctly, because the chunk answering the question never reached it.

Asked **"WHAT IS THE ADMISSION POLICY"** across 22 documents, that chunk ranked **7th at
0.588** — under the 0.60 floor and outside a top_k of 5. What cleared instead was a refunds
table and two page headers.

    "What is the admission process?"   0.623  admitted
    "Tell me about admission policy"   0.639  admitted   <- the phrasing that worked
    "WHAT IS THE ADMISSION POLICY"     0.588  CUT        <- the phrasing that "broke"

Case is irrelevant. **"policy" vs "process" is worth 0.035 and "tell me about" is worth
0.051** — enough to cross the floor either way, so the same question answered or refused
depending on wording.

**THREE OBVIOUS FIXES WERE MEASURED AND REJECTED** (`benchmarks/26_retrieval_gate.py`), and
that record is the valuable part:

| candidate | result |
| --- | --- |
| move the floor | **impossible in principle.** BACKLOG 20 measured the same floor as too *low* two days earlier. One number cannot do both jobs. |
| relative floor (ratio to top) | noise sits at **0.985** of its top hit, the wanted chunk at **0.862** of its own. No ratio separates them. |
| cross-encoder reranker | ms-marco-MiniLM-L-6-v2 over 20 candidates moved the chunk **7 → 8** and cost 2.1s/question. |
| smaller chunks | re-chunked the corpus at 256/192/128 tokens with the floor re-calibrated for each: **8/10, 7/10, 7/10** against 9/10 today. |

**BACKLOG 17 was also tested as a cause and ruled out:** stripping the repeated page header
moves the chunk 7 → 6 and does not change its score at all.

**THE FIX: anchored expansion** (`retrieval.py` decision 5). The top-scoring chunk names a
document; chunks from *that* document are admitted down to a lower floor (0.55), and top_k
rose 5 → 7 in both services. Measured over 13 questions:

                                target   off-document chunks   tokens/question
    today      0.60 / k=5         9/10                    14              1180
    flat       0.58 / k=7        10/10                    30              1940
    anchored   0.60 / k=7        10/10                    17              1661

It **cannot manufacture an answer**: expansion only runs when something already cleared the
real floor, so a question that retrieves nothing still returns `insufficient_context`. Held
by `test_expansion_cannot_fire_when_nothing_cleared_the_real_floor`.

**Both phrasings are now in the golden set** (`admission-policy`, `admission-process`) in the
user's own capitalisation, so this cannot regress quietly.

**What remains open:** the anchor floor of 0.55 clears the highest unanswerable golden
question (0.5175) by only **0.032**. That margin is thin and is the first thing to revisit if
a false answer ever appears on an unanswerable question. BACKLOG 20 stays open — anchored
expansion addresses recall, not the off-document noise that item is about.

### 25. ~~The runbook was wrong in three places~~ — **RESOLVED, M3 D19**
A clean-room run — both repositories cloned fresh, a new empty database, a new `venv`, a new
`npm install`, nothing but the commands in `README.md` — found three defects that reading it
could not. All three had been in place for as long as the instruction had.

**1. `./mvnw spring-boot:run` does not start the backend, and fails in the worst possible
way.** Day 17 made "no active profile" a refusal, and §4 was never updated. The reader sees

    Started KnowledgeAssistantApplication in 8.9 seconds     <- the line §4 says to wait for
    Refusing to start: app.jwt.secret is still the development default
    Process terminated with exit code: 1

so the documented success signal appears **and then the process dies**. The fix is
`SPRING_PROFILES_ACTIVE=dev`, which the error message itself names — the application was
clear and the runbook was not. Worth recording that the migrations complete before the
refusal, so nothing is left half-applied.

**2. `ruff` was never declared.** `requirements.txt` listed `pytest` under "Test-only" but
not `ruff`, which had been installed here by hand months ago and never written down. On a
fresh venv the lint command the README tells you to run fails with `No module named ruff`.
Now pinned at `0.9.6`. A gate nobody can run on a clean checkout is not a gate.

**3. The verification claim outran the evidence.** The file said it "was verified by
following it on this machine", inherited from when it covered one process. It now covers
four, and two steps are still genuinely unverified — building pgvector from source, and the
cold model download — so it says which.

**The cheap lesson:** every one of these is invisible to re-reading, because re-reading
happens on a machine where the missing thing is already present. The three facts corrected
on Day 19 by counting (`92 -> 197` tests, `V17 -> V20`, 13 -> 12 tables) were the same shape:
true once, never re-checked.

### 26. A typo loses the document entirely — *added M3 D19*
**Reported from real use, and it will happen again.** `tell me about ai saftey` returned
*"I couldn't find anything in your documents that answers that"* while `AI_safety.pdf` sat in
the corpus with **81 chunks**.

    "tell me about ai saftey"   top = 0.5355   CUT       <- best match was the wrong document
    "tell me about ai safety"   top = 0.7120   ADMITTED
    "ai safety"                 top = 0.7478   ADMITTED
    "what is ai safety"         top = 0.6861   ADMITTED

**One letter costs 0.177.** `bge-small` is character-sensitive and has no spell correction —
`saftey` is a different token sequence producing a different vector. It does not *nearly*
match; it lands somewhere else, and the nearest thing to it was a graded assessment CSV.

This is the same weakness as BACKLOG 24 at a larger magnitude: *"policy"* vs *"process"* was
worth 0.035, the *"tell me about"* framing 0.051, a typo **0.177**. Users type at the speed
of thought and will keep doing this.

**THE MESSAGE IS FIXED, THE RETRIEVAL IS NOT.** Day 19 made the reply distinguish a near miss
from a genuine one — it now says the closest passage fell just under the threshold and
suggests checking the spelling, rather than advising an upload of a document already present.
That turns a dead end into advice. It does not find the document.

**Verdict: DEBT.** The fix is a lexical pass alongside the vector search — trigram similarity
(`pg_trgm`, already available in Postgres) or BM25 — fused with the vector ranking. A
character-level index catches exactly what a bi-encoder cannot, and the two fail in
uncorrelated ways, which is the whole argument for hybrid retrieval. Measure against the
golden set plus a deliberately misspelled variant of each question before adopting it.

### 27. The embedding model is always local, including on the cloud backend — *added M3 D19*
**Not a defect — a property nobody had stated, and it surprises people.** Choosing "Cloud"
in the chat switches the **generation** model to Gemini. Retrieval does not move: the query
is embedded by `bge-small-en-v1.5` on this machine, and pgvector searches locally, on every
request regardless of backend.

Two consequences that follow, and both matter:

- **Cloud cannot rescue a retrieval failure.** If the embedder scores the right chunk under
  the floor, switching to Gemini changes nothing — the model is simply handed the same wrong
  chunks, faster. BACKLOG 24 and the typo above are invisible to the backend choice.
- **It is the reason the privacy story is as good as it is.** Only the chunks that already
  cleared the floor are sent to Google. The question is embedded locally, the corpus is
  searched locally, and the documents that did not match never leave the machine.

**Verdict: BY DESIGN, now documented.** Worth stating in `README.md` §3 next to the
`GENAI_GEMINI_API_KEY` warning, because "Cloud" reads like it moves everything and it moves
exactly one stage.

### 28. ~~The floor was the common cause of three separate complaints~~ — **RESOLVED, M3 D19**
Three reports in one week, each answered with a fix in FRONT of the floor rather than to it:

    admission chunk      0.588   floor 0.60   missed by 0.012   -> anchored expansion
    ai safety (typo)     0.535   floor 0.60                     -> spelling correction
    university policy    0.593   floor 0.60   missed by 0.007   -> (nothing; still failed)

The third is what made it undeniable: the user typed `polciy`, spelling correction fixed it
to `policy` exactly as designed, the corrected query scored **0.5926**, and it was *still*
cut. The fix worked and the answer still did not come, because the floor was never the
spelling.

`default_min_score` had been left at 0.60 twice with "deliberately NOT changed" in the commit
message. Measured properly in `benchmarks/27_retrieval_floor.py`:

| floor | golden | reported failures | leaked | noise | tokens/q |
|---|---|---|---|---|---|
| 0.50 | 9/9 | 5/5 | **2** | 36 | 2855 |
| 0.51 | 9/9 | 5/5 | **1** | 36 | 2855 |
| **0.55** | **9/9** | **5/5** | **0** | 29 | 2586 |
| 0.59 | 9/9 | 5/5 | 0 | 23 | 2270 |
| 0.60 *(before)* | 9/9 | **4/5** | 0 | 14 | 1709 |
| 0.63 | 8/9 | 3/5 | 0 | 2 | 1033 |

**THE CONSTRAINT IS NOT RECALL.** The floor is what produces `insufficient_context`, so a
floor below the best score an unanswerable question reaches makes the service answer things
the corpus cannot answer — invisibly. Measured ceiling **0.5175** ("Who won the 1998 FIFA
World Cup final?"), which is why 0.50 leaks and 0.52 does not.

**0.59 was rejected despite being cheaper**: it clears "university policy" by 0.0026, one
phrasing away from failing again, and phrasing sensitivity is the entire complaint. 0.55
gives that case 0.043 of headroom and sits 0.033 above the unanswerable ceiling.
`anchor_min_score` moved 0.55 → 0.50 with it, or the expansion band would have been empty
and silently disabled.

**The noise it created was then removed, not accepted.** Lowering the floor doubled
off-document chunks, 14 → 29. A relative floor does not separate them — right-document
chunks sit at 0.951 of the top score and off-document at 0.939, so any ratio cut loses
signal as fast as noise. What does separate them is that **the noise is off-DOCUMENT**, and
document selection is the one thing this embedder does reliably (9/9 on the golden set):

| policy | hits | off-document | tokens/q |
|---|---|---|---|
| 0.60, any document *(before)* | 13/14 | 14 | 1709 |
| 0.55, any document | 14/14 | 29 | 2586 |
| **0.55, top 1 document** | **14/14** | **0** | **1943** |
| 0.55, top 2 documents | 14/14 | 13 | 2268 |

`max_documents=1` is strictly better than the setting it replaces on every axis measured:
full recall, no off-document noise, and fewer prompt tokens than the 0.60 floor. BACKLOG 20
is superseded because its recommendation — raise the floor to 0.62 — was the opposite of
this and was measured against recall it did not have.

**A third problem only real questions could reveal.** The unanswerable golden questions
score 0.44–0.52, so 0.55 looked safe against them. Real off-topic questions score far
higher, because they share vocabulary with the corpus:

    what is university policy    0.5926   genuine
    Follow up on finance         0.5925   an aviation deck; this user has no finance document

**One ten-thousandth apart.** At 0.60 the second returned nothing; at 0.55 it returned seven
chunks of an unrelated deck for the model to write from — trading a missing answer for a
confidently wrong one, which is strictly worse.

No floor separates them. The **document margin** does, and only in the band where it is
needed. Measured over every real question in [0.55, 0.60):

    what is university policy    margin 0.0428   keep
    tell me about university     margin 0.0262   keep
    tell me in detail            margin 0.0114   refuse  (a bare follow-up)
    Follow up on finance         margin 0.0047   refuse
    tell me your bugs ?          margin 0.0017   refuse

5 of 5, with 0.015 between the weakest keep and the strongest refuse. Applied **only below**
`confident_score` (0.60): above it a match stands on its own, and "tell me about ai safety"
scores 0.7120 with a margin of 0.0148 because two documents both mention AI — not a reason
to answer nothing.

The pattern across all three mechanisms is the same: **this embedder is reliable about WHICH
DOCUMENT and unreliable about which chunk**, so every guard that works is a document-level
one and every chunk-level threshold tried here has failed.

### 29. A question needing two documents now sees one — *added M3 D19*
The cost of `max_documents=1`, and it is **untested rather than measured safe**. Nothing in
the golden set is cross-document: every question has a single `expect_document`, so the
evaluation that justified the limit is structurally blind to the case the limit would break.

A question like *"compare what the prospectus and the tracker say about deadlines"* would
now be answered from one of them, and nothing in the response would say the other was
dropped. The trace shows it — `document_ids` carries one entry — but no user reads a trace.

**Verdict: DEBT, cheap to fix when it appears.** `GENAI_MAX_DOCUMENTS=2` restores
two-document answers at a cost of 13 off-document chunks, and `0` disables the limit
entirely. The real fix is a golden question that genuinely spans two documents, so the
setting can be chosen on evidence rather than on the absence of it.

### 3a. Spring's GenAI client is hand-maintained against the FastAPI spec — *added M3 D1*
Item 3 again, on a boundary one day old. The Python service publishes an OpenAPI spec generated from the same Pydantic models that validate its requests, so *that* side cannot drift from itself. **Spring's client can.** The Java classes that call `/ingest`, `/answer` and `/retrieve` are written by hand, and nothing compares them to the spec.

Saying "FastAPI gives us a single source of truth" and stopping there would repeat Month 2 exactly: the spec is the foundation for a fix, not the fix. The mechanism is one of (a) generate the client from `/openapi.json` at build time, or (b) a test that fetches the spec and asserts Spring's request/response classes still match it.

Until one exists, `extra="forbid"` on every Pydantic model is the stopgap — an unknown field from Spring is a `422` on the first request instead of a value quietly ignored for a fortnight. That catches Spring sending too much. It does not catch Spring *reading* a response field that has been renamed. **Verdict: DEBT.** Cheap now, while there is exactly one consumer and three endpoints.

---

### 14. The GenAI service's test seams are monkeypatched module globals — *added M3 D15*

Day 15 took `app/routers/answer.py` from 38% to 93% and `app/generation.py` from 19% to 98%, and the way in was `monkeypatch.setattr` on module-level names: `registry.embedder`, `registry.tokenizer`, `answer_router.run_retrieval`, `generation.httpx.post`.

**It works and it is the wrong seam.** Those tests assert on the *structure of the module* as much as on its behaviour — rename `run_retrieval` to `search`, move the registry lookup into a helper, and tests that have nothing to do with either go red. A test that breaks for a reason unrelated to what it claims to check is a test people learn to ignore.

The right seam is **FastAPI dependency overrides**: make `_embedder`, `_generator` and `_route` dependencies, and let tests supply fakes through `app.dependency_overrides`. It is the framework's own idiom, it makes the injection points visible in the signature rather than discoverable only by reading the tests, and it removes every `monkeypatch.setattr` on a module global.

Chosen deliberately on the day: Day 15 is a *testing* day, and a production refactor to make testing prettier is how a testing day becomes a refactoring day with untested code at the end of it. The coverage was the deliverable; the seam is the follow-up.

**Verdict: DEBT, small and well-bounded.** One module, three functions, and the tests that would have to change are all new and all in one directory. Natural home is Day 17 (configuration and secrets) or Day 20 (final hardening).

---

## MONTH 3 — correctly waiting on AI work

### 4. `ActionStatus.failed` is never produced
Exists for real tool execution that can fail. Today every approved action is a database insert that either works or throws. **Verdict: MONTH 3.**

### 5. `DocumentStatus.processing` / `failed` never produced
Describe a chunk → embed → index pipeline that does not exist. A document is `ready` once its bytes land, which is the truth today. **Verdict: MONTH 3** (tracker days 3–5).

### 6. Citation source selection is a placeholder
The citation *pipeline* is real — row, API shape, rendered card, ownership-scoped. Only the choice of which document is a deterministic stand-in for retrieval. **Verdict: MONTH 3** (tracker day 7); nothing downstream changes when it lands.

### 7. Task-creation trigger is keyword matching
`TASK_TRIGGERS` is a phrase list. Real tool-calling replaces it. **Verdict: MONTH 3** (tracker days 10–11).

**M3 D14b — PARTIALLY FIXED, and the honest version is more interesting than "replaced".** The phrase list moved from `ChatSessionService` to `genai-service/app/intent.py` and now sits behind a trained classifier over the bge vectors retrieval already computes. Measured on 27 held-out cases: keywords alone 25/27, classifier alone **24/27**, both together **26/27**, all with zero false positives.

**The keyword list was not replaced, because it is still the better half for `create-task`.** The classifier *lost* on its own. What it adds is the two tools no phrase list can express without colliding with ordinary questions — "summarise the runway efficiency figures" wants an answer, "summarise the AeroTwin document" wants the tool — plus generalisation to phrasings nobody wrote down ("could you jot down that…" matches no trigger and routes correctly).

So the resolution is not "real tool calling replaced keywords". It is: *one* router now exists instead of three copies, keywords decide where a readable auditable rule applies, and a classifier covers what a rule cannot express. **M3 D15 — the remaining half is now fixed too.** Title extraction was still a fixed list of complete prefixes while the classifier was routing phrasings nobody had written down. Measured on 32 create-task messages drawn from the two routing files: **11/32 correct, and 16 of them became their own title verbatim.**

Measuring it also surfaced two bugs that were invisible from reading the list: *dangling connectives* ("make a task to chase the vendor invoice" → "To chase the vendor invoice", because "make a task" was listed and "make a task to" was not) and *over-stripping* ("please follow up on the runway inspection" → "The runway inspection", because "follow up on" was in the list when it is the WORK). Over-stripping is the harder error to see, because the output still reads like English.

Fixed by peeling wrappers **compositionally** rather than matching whole prefixes — "can you" + "write down" + "that" are three independent layers, and enumerating their combinations is the combinatorial problem the classifier was brought in to avoid. **32/32** on the measured set and 14/15 on phrasings written after the fact.

**Verdict: RESOLVED.** One router, one title extractor, both generalising. See `tests/test_title_extraction.py` — 90 tests, including an assertion that every case message comes from a file written before this fix, so the set cannot be gamed later.

---

## BY DESIGN — deliberate, fine indefinitely

### 8. Message transcript is not paged
Paging a conversation needs a load-older interaction, not an envelope. A numbered pager on a chat would be worse than none. **Verdict: BY DESIGN** until the UI pattern is built; revisit if a transcript gets long enough to matter.

### 9. Action proposals are ephemeral
Never persisted, so history returns messages without them. This is the governance model, not an oversight: the assistant proposes, a human decides, and only an approval writes anything. The consequence — clients must retain them locally — is documented in the contract.

### 10. Mail off unless credentials exist
The reset link goes to the log with no credentials configured. Keeps the flow testable with no secret committed. **Verdict: BY DESIGN.**

### 11. `FRONTEND_BASE_URL` defaults to localhost
Reset links only resolve on the machine running the app. Correct for local development; an environment variable exists for anything else. **Verdict: BY DESIGN**, documented in the runbook.

### 12. No `docker-compose.yml`
Docker is unavailable on the development machine, so any compose file would be untested — and a documented path that fails costs a reader more than an absent one. **Verdict: BY DESIGN**, with the facts a Docker user needs given in the README instead.

### 13. Client-side role check on the admin route
Hides a door rather than locking one. The lock is `/api/admin/**` returning 403 server-side regardless of what the client renders. Both exist on purpose. **Verdict: BY DESIGN.**

---

## DONE — closed this month, recorded so they stop being asked about

| | |
|---|---|
| Multi-user scoping | Day 16 — every read and write scoped; cross-user is 404 |
| Document download | Day 16 — needed `owner_id` first, which is why it waited |
| Delete chat / delete document | Day 16 — the document DELETE had never existed while the UI called it |
| Full Spring Security + JWT | Day 16 |
| Sign-up, password reset | Day 16 |
| Credentials in logs | Day 17 — Logbook removed, guarded by a test |
| JSON structured logging | Day 20 — deferred from Day 17 until a runnable prod profile made it checkable |
| Pagination | Day 19 |
| Flyway baseline trap | Day 20 |
| Admin UI / sign-out-everywhere | Day 21 — the last two unreachable endpoints |

---

## Unreached endpoints do not merely sit unused — they drift

A compounding version of the pattern, and the sharper lesson from Day 21.

`/api/admin/users` passed all three audit diffs: it existed, it was role-gated, it was correct by URL. It was wrong only in **shape** — still returning a bare array after every sibling had moved to the paged envelope. It was skipped by the Day-19 pagination sweep for exactly one reason: **nothing called it, so nothing broke.**

The mechanism that normally catches a missed refactor is a consumer failing. An endpoint with no consumer has no such mechanism, so it silently falls behind its siblings and the divergence is only discovered when someone finally connects it — by which time it has been wrong for days.

That is an argument for reaching endpoints promptly which is **independent** of the "users cannot use it" argument. Even a capability nobody needs yet should have a consumer, if only a test, because the consumer is what keeps it honest through refactors.

## The pattern worth carrying into Month 3

Six times this month a backend capability was complete, correct, and unreachable: the audit trail, the governance loop, both DELETEs, citations, and the admin endpoint. A seventh — the Documents delete button — was the mirror image, a UI control calling an endpoint that never existed.

They share a cause: the work is sequenced by **layer**, so "the endpoint works" and "a user can do it" were never the same milestone, and nothing in between them ever checked.

Two questions at the end of any backend change would have caught every one:

1. **What does a user click to reach this?**
2. **If the answer is "nothing yet", is that written down as deliberate?**

Item 3 above is the mechanised version of the same check, and is why it is the highest-value item in this file.
