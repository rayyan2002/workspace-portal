# Review command sheet — every claim, one command

Copy-paste, top to bottom. Each block prints the evidence for one claim.

## Setup (once)

```bash
brew services start postgresql@16
```

Every command below is run from `backend/genai-service`, so start there:

```bash
cd backend/genai-service
```

---

## "Is it tested?"

**78 tests, clean lint, clean types.**

```bash
./.venv/bin/python -m pytest tests
```

```bash
./.venv/bin/python -m ruff check app tests benchmarks
```

```bash
./.venv/bin/python -m pyright app tests
```

---

## "Does the service run?"

Leave this one running and use a second terminal for the rest of this section.

```bash
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Liveness answers instantly, even while models load:**

```bash
curl -sS http://127.0.0.1:8000/health/live
```

**Readiness reports which models and which pinned revisions:**

```bash
curl -sS http://127.0.0.1:8000/health/ready | python3 -m json.tool
```

**Every endpoint is declared but honest about being unimplemented:**

```bash
curl -sS -X POST http://127.0.0.1:8000/answer -H 'Content-Type: application/json' -d '{"question":"anything","allowed_document_ids":[]}'
```

**An empty allowed list is ACCEPTED — a user with no ready documents is normal, not an attack:**

```bash
curl -sS -o /dev/null -w 'empty list -> HTTP %{http_code}\n' -X POST http://127.0.0.1:8000/answer -H 'Content-Type: application/json' -d '{"question":"x","allowed_document_ids":[]}'
```

**Omitting the field is a 422 — that is Spring's bug, and it should be loud:**

```bash
curl -sS -X POST http://127.0.0.1:8000/answer -H 'Content-Type: application/json' -d '{"question":"x"}' | python3 -m json.tool
```

**An unknown field is rejected rather than ignored — drift fails on the first request:**

```bash
curl -sS -X POST http://127.0.0.1:8000/answer -H 'Content-Type: application/json' -d '{"question":"x","allowed_document_ids":[],"temperature":0.7}' | python3 -m json.tool
```

**The spec generated from the code itself:**

```bash
curl -sS http://127.0.0.1:8000/openapi.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('paths:', *sorted(d['paths']), sep='\n  ')"
```

Or open `http://127.0.0.1:8000/docs` in a browser.

---

## "Show me the numbers" — Day 3, chunking

**Every real document extracts; all 8 PDFs have a text layer, so no OCR is needed:**

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/01_extract_corpus.py
```

**177 chunks from 21 documents, none over the ceiling, every offset verified:**

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/02_chunk_corpus.py
```

**Why the ceiling is 510 and not 512 — truncation is silent, `cosine = 1.000000`:**

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/09_truncation_is_silent.py
```

---

## "Show me the numbers" — Day 4, embeddings

**177 vectors, all unit norm, none NaN, 0.11 s per chunk:**

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/03_embed_corpus.py
```

**170 of 173 cross-document neighbours are identical text (the duplication *structure*):**

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/04_corpus_duplication.py
```

**And the multiple itself, straight from SQL — 2.72x by chunk, 2.10x by document:**

```bash
psql -d knowledge_assistant -c "SELECT count(*) chunks, count(DISTINCT md5(text)) distinct_texts, round(count(*)::numeric/count(DISTINCT md5(text)),2) ratio FROM document_chunks;"
```

**Batch 1 is fastest, in BOTH sweep directions — so it is not thermal throttling (~3 min):**

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/05_batch_size_sweep.py
```

**Sequence length is what decides whether batching helps (~1 min):**

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/06_batch_vs_length.py
```

**The experiment that DISPROVED my explanation — kept deliberately (~2 min):**

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/07_batch_vs_threads.py
```

---

## "How slow is an answer?"

**15.5–18.7 s end to end on a real 16-page PDF (~2 min):**

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/08_answer_latency.py
```

---

## "Show me the prompt work" — Day 2

**The three templates and what each costs in prefill:**

```bash
PYTHONPATH=$PWD ./.venv/bin/python -c "from transformers import AutoTokenizer; from app.config import settings; from app.prompts.templates import ALL_TEMPLATES; t=AutoTokenizer.from_pretrained(settings.embedding_model, revision=settings.embedding_model_revision); [print(f'{x.version:14s} {len(t.encode(x.system)):4d} tokens') for x in ALL_TEMPLATES]"
```

**qa-v2 renders context with NO `[n]` labels — the labels taught the model to copy them:**

```bash
PYTHONPATH=$PWD ./.venv/bin/python -c "from app.prompts import QA_V1, QA_V2; c=['Employees get 12 weeks.','Managers approve leave.']; print('--- qa-v1 ---'); print(QA_V1.render(c,'q?').user); print(); print('--- qa-v2 ---'); print(QA_V2.render(c,'q?').user)"
```

**The parser survives the shape the model actually returns, not the one it was asked for:**

```bash
PYTHONPATH=$PWD ./.venv/bin/python -c "from app.prompts import parse_answer; print(parse_answer('{\"answer\":\"12 weeks.\",\"cites\":[{\"number\":1,\"context\":\"[1]\"}]}', 3))"
```

**A quote that matches no chunk is DROPPED, not guessed — the property cite-by-number could not have:**

```bash
PYTHONPATH=$PWD ./.venv/bin/python -c "from app.prompts import parse_quoted_answer; c=['Employees get 12 weeks of leave.','Managers approve it.']; print(parse_quoted_answer('{\"answer\":\"x\",\"quotes\":[\"the sky is green in winter\"]}', c))"
```

**Tool proposals map exactly onto Spring's CreateTaskPayload — hyphens, title + priority:**

```bash
PYTHONPATH=$PWD ./.venv/bin/python -c "from app.schemas import ToolProposal; import json; p=ToolProposal.model_validate({'label':'Create a tracking task','arguments':{'tool':'create-task','title':'Review the leave policy','priority':'medium'}}); d=p.model_dump(mode='json'); print(json.dumps({'type':d['arguments']['tool'],'label':d['label'],'payload':{k:v for k,v in d['arguments'].items() if k!='tool'}}, indent=2))"
```

**`create_task` with an underscore is now a REJECTED tag — the naming cannot drift back:**

```bash
PYTHONPATH=$PWD ./.venv/bin/python -c "from app.schemas import ToolProposal; ToolProposal.model_validate({'label':'x','arguments':{'tool':'create_task','title':'t','priority':'low'}})" 2>&1 | tail -3
```

---

## "Where is that in the code?"

```bash
sed -n '54,80p' app/models_registry.py     # background loading + _fail_remaining
```

```bash
sed -n '246,300p' app/prompts/parsing.py   # resolve_quote, parse_quoted_answer
```

```bash
sed -n '81,120p' app/ingestion/chunk.py    # sentence-aware packing
```

```bash
sed -n '40,95p' app/ingestion/embed.py     # the batch-size measurement, in a comment
```

```bash
grep -n "^| [0-9]" ../INTEGRATION_CONTRACT.md   # all 7 contract revisions
```

---

## "Is the threshold in the right place?" (Day 6)

**The noise floor, and which anchors are lying to you:**

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/13_threshold_calibration.py
```

**Duplicate collapsing, on the live corpus** — five copies of one passage become one:

```bash
curl -sS -X POST http://127.0.0.1:8000/retrieve -H 'Content-Type: application/json' -d "{\"question\":\"What were the quarterly financial results?\",\"allowed_document_ids\":[$(psql -d knowledge_assistant -At -c "select string_agg('\"'||id||'\"',',') from documents where owner_id='83814a60-6bd4-427a-8382-8972debaa6ca';")]}" | python3 -m json.tool
```

**The empty allow-list is legal and returns nothing** (not everything):

```bash
curl -sS -X POST http://127.0.0.1:8000/retrieve -H 'Content-Type: application/json' -d '{"question":"What is covered in the GenAI training tracker?","allowed_document_ids":[]}' | python3 -m json.tool
```

**The filter is the only control, tested with the threshold disabled** — ask for user A's
document while passing user B's allow-list and `min_score=-1.0`:

```bash
curl -sS -X POST http://127.0.0.1:8000/retrieve -H 'Content-Type: application/json' -d "{\"question\":\"What does the AeroTwin defense preparation document cover?\",\"min_score\":-1.0,\"allowed_document_ids\":[$(psql -d knowledge_assistant -At -c "select string_agg('\"'||id||'\"',',') from documents where owner_id='5eb35438-34df-4893-9012-7c596ecf08f5';")]}" | python3 -m json.tool
```

---

## "Does it answer, and does it cite?" (Day 7)

**Greedy vs sampled, JSON rate, citation rate** — the numbers behind the decoding default:

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/14_decoding_and_citations.py
```

**A grounded answer with citations** (slow — 30 s or so, and the model is the whole cost):

```bash
curl -sS -X POST http://127.0.0.1:8000/answer -H 'Content-Type: application/json' -d "{\"question\":\"What does the AeroTwin document say about the demo?\",\"allowed_document_ids\":[$(psql -d knowledge_assistant -At -c "select string_agg('\"'||id||'\"',',') from documents where owner_id='83814a60-6bd4-427a-8382-8972debaa6ca';")]}" | python3 -m json.tool
```

**insufficient_context never reaches the model** — `prompt_tokens: 0`, `generate_ms: 0`,
and the whole call under 50 ms:

```bash
curl -sS -X POST http://127.0.0.1:8000/answer -H 'Content-Type: application/json' -d "{\"question\":\"What is the capital of France?\",\"allowed_document_ids\":[$(psql -d knowledge_assistant -At -c "select string_agg('\"'||id||'\"',',') from documents where owner_id='83814a60-6bd4-427a-8382-8972debaa6ca';")]}" | python3 -m json.tool
```

---

## "Show me what actually happened" — one live query, explained

For a demo, or for answering "why did it say that?". Re-runs a question against the
running service and joins the trace back to Postgres, so UUIDs become filenames, pages and
text. Read-only: it changes nothing.

Seven sections — the corpus it searched, how the question became a search, every chunk that
matched with its score, the generation cost, whether the answer was made of the documents,
which sentence was cited, and what the user saw.

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/19_explain_query.py "What does the AeroTwin document say about the demo?"
```

**Retrieval only** — skips the 15-60s generation, so it answers instantly. Best for showing
scoring and duplicate collapsing:

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/19_explain_query.py "how many parts in project_setup.txt" --retrieve-only
```

**The guard refusing to answer** — a question the documents cannot answer, where the model
would otherwise invent one:

```bash
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/19_explain_query.py "tell me about how to defend fyp"
```

---

## "Has the contract drifted?" (Day 13)

Spring's client is hand-written against the FastAPI spec — BACKLOG.md item 3a. The Python
side generates `/openapi.json` from the same Pydantic models that validate its requests, so
it cannot drift from itself. Spring can.

`GenAiSpecConformanceTest` derives its assertions FROM the committed spec at
`src/test/resources/genai-openapi.json`, so a rename on the Python side fails the Spring
build rather than 422-ing in production.

**Is the committed snapshot still what the service publishes?** Run this after any change
to `schemas.py`. It needs the service up, which is why it is a command and not a test —
a Spring test that depends on a Python process being alive is the trap Day 8 caught.

```bash
curl -s http://127.0.0.1:8000/openapi.json | ./.venv/bin/python -c "import json,sys; json.dump(json.load(sys.stdin), open('/tmp/live-spec.json','w'), indent=2, sort_keys=True)" && diff <(cat /tmp/live-spec.json) <(python3 -c "import json;print(json.dumps(json.load(open('../src/test/resources/genai-openapi.json')), indent=2, sort_keys=True))") && echo "IN SYNC" || echo "DRIFTED — refresh the snapshot"
```

**Refresh the snapshot** when the drift is intentional:

```bash
curl -s http://127.0.0.1:8000/openapi.json | ./.venv/bin/python -c "import json,sys; json.dump(json.load(sys.stdin), open('openapi.json','w'), indent=2, sort_keys=True); open('openapi.json','a').write(chr(10))" && cp openapi.json ../src/test/resources/genai-openapi.json && echo "snapshot refreshed — now run the Spring tests"
```

**Prove the check works** by mutating the snapshot and watching the build fail:

```bash
cp src/test/resources/genai-openapi.json /tmp/spec.bak && python3 -c "import json;p='src/test/resources/genai-openapi.json';s=json.load(open(p));r=s['components']['schemas']['RetrievalRequest'];r['properties']['allowed_docs']=r['properties'].pop('allowed_document_ids');json.dump(s,open(p,'w'),indent=2,sort_keys=True)" && ./mvnw -o test -Dtest=GenAiSpecConformanceTest; cp /tmp/spec.bak src/test/resources/genai-openapi.json
```

---

## Day 14b — tool routing

**Does the classifier beat the keyword list it replaced?** The headline comparison, on the
27 held-out cases in `evaluation/tool_cases.json`. Fails hard if the train and test splits
overlap, because a classifier scored on its own training data reports its memory.

```bash
./.venv/bin/python benchmarks/23_intent_classifier.py
```

**The routing evaluation, through the REAL router** — `app.intent`, the same code the
product runs, not a reimplementation of it:

```bash
./.venv/bin/python benchmarks/22_tool_evaluation.py
```

**The router this replaced**, for comparison. It cannot emit `summarize-document` or
`lookup-knowledge` at all, so both are structural misses for it:

```bash
./.venv/bin/python benchmarks/22_tool_evaluation.py --keywords-only
```

**Routing accuracy as a test.** Needs the embedding model (~130MB, ~2s) and no database, so
it is opt-in like the golden set:

```bash
./.venv/bin/python -m pytest tests/test_intent.py -m routing -q
```

**The three languages, held to one contract.** Each of these reads a committed artefact
rather than another language's prose:

```bash
cd .. && ./mvnw -o test -Dtest='ToolRegistryConformanceTest+ActionContractSnapshotTest+GenAiSpecConformanceTest'
```

```bash
cd ../../frontend && npx vitest run src/Type.conformance.test.ts
```

**Prove the frontend check works** by renaming a field in the shared snapshot and watching
TypeScript's side go red:

```bash
cd ../../frontend && cp src/test/action-contract.json /tmp/ac.bak && sed -i '' 's/"documentId", "documentName"/"docId", "documentName"/' src/test/action-contract.json && npx vitest run src/Type.conformance.test.ts; cp /tmp/ac.bak src/test/action-contract.json
```

**Refresh the tool registry snapshot** after any change to the argument schemas. One command
writes all three copies, so they cannot be refreshed unevenly:

```bash
./.venv/bin/python -c "import sys,json;sys.path.insert(0,'.');from app.routers.tools import tools;o=json.dumps(tools().model_dump(mode='json'),indent=2,sort_keys=True)+chr(10);open('evaluation/tool_registry.json','w').write(o);open('../src/test/resources/tool-registry.json','w').write(o);open('../../frontend/src/test/tool-registry.json','w').write(o);print('refreshed 3 copies')"
```

---

## Day 15 — measuring the test suite

**Is the suite as covered as it claims?** `pytest-cov` is deliberately NOT pinned in
`requirements.txt` — it is used occasionally and that file carries a long warning about
pinning fragility on this machine — so the install is part of the command:

```bash
./.venv/bin/pip install --quiet pytest-cov==5.0.0 && ./.venv/bin/python -m pytest tests -m "not golden" --cov=app --cov-report=term-missing -q
```

Measured on Day 15: **97%**, up from 79% at the start of the day. Remove it again afterwards
so the pinned environment stays exactly what `requirements.txt` describes:

```bash
./.venv/bin/pip uninstall -y pytest-cov coverage && rm -rf .venv/lib/python3.11/site-packages/pytest_cov && ./.venv/bin/python -c "import torch,numpy,sklearn;print('pins intact:',torch.__version__,numpy.__version__,sklearn.__version__)"
```

The `rm -rf` is not belt-and-braces: pip leaves an empty `pytest_cov/__pycache__` behind, so
`import pytest_cov` still SUCCEEDS afterwards as a namespace package. Checking
`pytest_cov.__file__ is None` is what distinguishes it from a real install.

**The whole suite, both markers:**

```bash
./.venv/bin/python -m pytest tests -q && ./.venv/bin/python -m pytest tests -m routing -q
```

---

## Day 16 — ingestion and citation recovery

**Does an uploaded document actually become searchable?** The whole point of Day 16. Upload
through the UI, then check the row and its chunks:

```bash
./.venv/bin/python -c "import sys;sys.path.insert(0,'.');from app.config import settings;import psycopg;c=psycopg.connect(settings.dsn);[print(r) for r in c.execute('select d.filename, d.status, count(ch.id) chunks, max(ch.embedding_model) from documents d left join document_chunks ch on ch.document_id=d.id group by d.id, d.filename, d.status order by d.upload_date desc limit 5').fetchall()]"
```

**Ingest a file directly, bypassing Spring.** Useful for timing and for proving the service
writes nothing — run it twice and the chunk count in Postgres does not change:

```bash
curl -s -X POST http://127.0.0.1:8000/ingest -F "file=@uploads/<document-id>;type=application/pdf" -F "document_id=<document-id>" -F "filename=x.pdf" -F "content_type=application/pdf" | ./genai-service/.venv/bin/python -c "import json,sys;r=json.load(sys.stdin);t=r['trace'];print(f\"{r['chunk_count']} chunks  extract {t['extract_ms']}ms  embed {t['embed_ms']}ms  total {t['total_ms']}ms\")"
```

**Citation recovery, before and after.** One generation per question, both strategies
computed from that identical reply — two runs against two builds would compare two different
model outputs. Withheld answers are excluded, because a suppressed answer has no citations a
user could see:

```bash
./.venv/bin/python benchmarks/24_citation_recovery.py
```

**Why a citation is missing, for one question.** `parse_path` is the diagnosis:
`json` means the model kept to the envelope, `text_fallback` means it wrote prose,
`salvaged_json` means the object would not parse. `citation_source` says which mechanism
produced what shipped:

```bash
curl -s -X POST http://127.0.0.1:8000/answer -H 'Content-Type: application/json' -d '{"question":"Tell me about admission policy","allowed_document_ids":["<doc-id>"],"model":"local","include_raw":true}' | ./.venv/bin/python -c "import json,sys;r=json.load(sys.stdin);t=r['trace'];print('parse_path     :',t['parse_path']);print('citation_source:',t['citation_source']);print('citations      :',len(r['citations']));print('overlap        :',round(t['grounding_overlap'],2));print('RAW            :',repr((t['raw_model_reply'] or '')[:300]))"
```

**NOTE — `--reload` and benchmarks do not mix.** The dev server watches the whole tree, so
any file written while a benchmark runs restarts it and the two models take ~45s to come
back. The benchmark waits for `/health/ready` and retries, but the run takes much longer.
Start the service without `--reload` when measuring.
