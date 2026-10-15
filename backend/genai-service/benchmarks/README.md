# Benchmarks — every number in NOTES.md and REVIEW_MAP.md, reproducible

These are the scripts that produced the measurements quoted elsewhere. They are here so a
claim can be **re-run** rather than believed. Several read the live `knowledge_assistant`
database and the real `uploads/` directory, so Postgres must be running.

```bash
cd genai-service
PYTHONPATH=$PWD ./.venv/bin/python benchmarks/02_chunk_corpus.py
```

| # | Script | Proves | Time |
|---|---|---|---|
| 01 | `01_extract_corpus.py` | Every real document extracts; all 8 PDFs have a text layer, so **no OCR needed** | ~15 s |
| 02 | `02_chunk_corpus.py` | **177 chunks from 21 documents**, none over the 510 ceiling, **every char offset verified** against the extracted text | ~20 s |
| 03 | `03_embed_corpus.py` | **177 vectors, all unit norm**, none NaN/inf, 0.11 s per chunk | ~1 min |
| 04 | `04_corpus_duplication.py` | 170/173 cross-document nearest neighbours are byte-identical text. (Multiple measured separately by SQL: **2.72x** by chunk, **2.10x** by document — this script shows the *structure*, not the ratio) | ~1 min |
| 05 | `05_batch_size_sweep.py` | **Batch 1 is fastest**, in both sweep directions — so it is not thermal throttling | ~3 min |
| 06 | `06_batch_vs_length.py` | **Sequence length** decides whether batching helps: crossover between 120 and 360 tokens | ~1 min |
| 07 | `07_batch_vs_threads.py` | The core-saturation explanation is **wrong** — at 6 threads with short chunks, batch 16 wins | ~2 min |
| 08 | `08_answer_latency.py` | End-to-end answer latency on a real 16-page PDF: **15.5–18.7 s** | ~2 min |
| 09 | `09_truncation_is_silent.py` | Why the ceiling is 510, not 512 — a 1,145-token text and its 510-token prefix embed to **cosine 1.000000** | ~20 s |
| 10 | `10_batch_vs_heterogeneity.py` | **The answer to 05**: padding from mixed chunk lengths. Uniform chunks → batching wins (0.89); mixed → batching loses badly (3.72) | ~1 min |

## Notes on reading these

**Read 05, 06, 07 and 10 as one argument, in that order.** 05 finds the effect. 06 and 07
kill two explanations for it — core saturation and sequence length. 10 finds the real cause:
padding from heterogeneous chunk lengths. Two discarded hypotheses are kept deliberately,
because "we tested this and it was wrong" is a result, and the next person should start from
the evidence rather than from a confident sentence.

**Numbers will not match to the decimal.** This is a laptop, it throttles, and other
processes compete. What should reproduce is the *ranking* and the *order of magnitude* — if
batch 64 ever beats batch 1 on this corpus, that is worth investigating.

**The prompt experiments from Day 2 are not here.** They each take 5–10 minutes of generation
and were exploratory rather than load-bearing; their results are recorded in `NOTES.md` with
the raw output quoted. If one needs re-running, say so and it can be restored.
