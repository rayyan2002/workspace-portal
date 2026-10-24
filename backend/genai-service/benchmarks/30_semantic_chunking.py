"""Day 20: semantic chunking against sentence packing, on the real corpus.

WHY THIS EXISTS. The chunker was changed on instruction, and an instruction is a decision
rather than a measurement. This is the measurement, so the decision can be defended with
numbers instead of opinion — and so a regression is found here rather than by a user.

WHAT IS COMPARED. The SAME files, extracted once, chunked both ways, embedded with the same
model, then asked the same questions. Nothing is written to Postgres: re-chunking in
production means re-uploading documents through Spring (rule R1 — Python holds SELECT only),
and a decision this size should be made before anything is migrated.

WHAT TO LOOK AT, in order:

  document hit   does the right DOCUMENT still win? This embedder is reliable about which
                 document and unreliable about which chunk; a drop here is a real loss.
  chunk hit      does the chunk that actually answers still get retrieved?
  noise          chunks admitted from the wrong document. Lower is better.
  tokens/q       what the model is asked to read. Larger chunks cost more per question.
  ingest         the real price of semantic: an embedding pass over every sentence.

    ./.venv/bin/python benchmarks/30_semantic_chunking.py
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from app.config import settings  # noqa: E402
from app.ingestion.chunk import chunk_document  # noqa: E402
from app.ingestion.extract import extract  # noqa: E402

GOLDEN = ROOT / "evaluation" / "golden_questions.json"
UPLOADS = ROOT.parent / "uploads"

#: Retrieval is always scoped to one user's documents, so the measurement is too.
OWNER_EMAIL = "mayub@nisum.com"

REPORTED = [
    ("what is university policy", "University_Admission_Prospectus_2027.pdf"),
    ("what is the admission process?", "University_Admission_Prospectus_2027.pdf"),
    ("tell me about ai safety", "AI_safety.pdf"),
    ("summarize features of swift", "Suzuki_Swift_2026_Pakistan_Guide.pdf"),
    ("summarize ai safety document abstract", "AI_safety.pdf"),
]


def main() -> None:
    golden = json.loads(GOLDEN.read_text())["questions"]
    answerable = [(q["question"], q["expect_document"], q.get("expect_chunk_contains"))
                  for q in golden if q["answerable"]]
    unanswerable = [q["question"] for q in golden if not q["answerable"]]
    cases = answerable + [(q, d, None) for q, d in REPORTED]


    with psycopg.connect(settings.dsn) as conn:
        # SCOPED TO ONE OWNER, and that is not tidiness. This database holds the same
        # files uploaded by three different people, and retrieval always runs against an
        # allow-list of ONE user's documents. Measuring across all of them scores a corpus
        # nobody can actually search, and inflates both the chunk count and the noise.
        documents = conn.execute(
            "SELECT d.filename, d.storage_path FROM documents d JOIN users u "
            "ON u.id = d.owner_id WHERE d.status = 'ready' AND u.email = %s "
            "ORDER BY d.filename", (OWNER_EMAIL,)).fetchall()
    # ONLY QUESTIONS THIS CORPUS CAN ACTUALLY ANSWER. The golden set was written against a
    # larger corpus; a question whose expected document is not present is unreachable for
    # EVERY strategy, and counting it makes a scoreboard that looks like failure and moves
    # for no reason. Scoring 6/14 when 7 of the 14 are unreachable says nothing at all.
    present = {filename for filename, _path in documents}
    unreachable = [(q, d) for q, d, _c in cases if d not in present]
    cases = [(q, d, c) for q, d, c in cases if d in present]

    model = SentenceTransformer(
        settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")

    def tokens(text: str) -> int:
        return len(model.tokenizer.encode(text, add_special_tokens=False))

    def embed(texts):
        return model.encode(list(texts), batch_size=8, show_progress_bar=False,
                            normalize_embeddings=True)

    extracted = []
    for filename, storage_path in documents:
        path = ROOT.parent / storage_path
        if not path.exists():
            print(f"  skipped (file missing): {filename}")
            continue
        try:
            extracted.append((filename, extract(path.read_bytes(), filename)))
        except Exception as unreadable:                              # noqa: BLE001
            print(f"  skipped ({type(unreadable).__name__}): {filename}")

    print(f"\n  {len(extracted)} documents re-extracted from disk (owner: {OWNER_EMAIL})")
    print(f"  {len(cases)} answerable questions, {len(unanswerable)} unanswerable")
    if unreachable:
        print(f"  {len(unreachable)} question(s) SKIPPED — their document is not in this "
              f"corpus, so no strategy could hit them:")
        for question, want in unreachable[:6]:
            print(f"      {question[:46]:46} wants {want[:34]}")
    print()

    # SWEPT, not guessed. The percentile is the only real knob semantic chunking has, and
    # picking it by eye is how a strategy gets blamed for a threshold. Higher = fewer cuts =
    # larger chunks, which on this corpus is the direction that matters: the sentence packer
    # it replaces produces a median of 478 tokens, and a 131-token chunk cannot carry the
    # context an answer needs.
    # SWEPT OVER THE ABSOLUTE FLOOR, which is now the gate that matters. The percentile was
    # demoted to a safety valve after it was found to fix the CUT COUNT rather than the cut
    # quality — on 55 gaps, p99 selects 0.55 of them regardless of what the text says.
    strategies = {"sentence (current)": dict(embed_sentences=None)}
    for floor in (0.35, 0.40, 0.45, 0.50):
        strategies[f"semantic d{floor:.2f}"] = dict(
            embed_sentences=embed,
            breakpoint_percentile=settings.semantic_breakpoint_percentile,
            window_sentences=settings.semantic_window_sentences,
            min_distance=floor,
            min_sentences=settings.semantic_min_sentences)

    results = {}
    for label, options in strategies.items():
        t0 = time.perf_counter()
        corpus = []           # (filename, text)
        for filename, document in extracted:
            for chunk in chunk_document(document, count_tokens=tokens,
                                        max_tokens=settings.max_chunk_tokens, **options):
                corpus.append((filename, chunk.text))
        chunk_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        vectors = embed([text for _fn, text in corpus])
        embed_ms = (time.perf_counter() - t1) * 1000

        sizes = [tokens(text) for _fn, text in corpus]
        results[label] = dict(corpus=corpus, vectors=vectors, chunk_ms=chunk_ms,
                              embed_ms=embed_ms, sizes=sizes)

    qvecs = {q: v for (q, _d, _c), v in zip(
        cases, embed([settings.query_prefix + q for q, _d, _c in cases]),
        strict=True)}
    uvecs = {q: v for q, v in zip(
        unanswerable, embed([settings.query_prefix + q for q in unanswerable]),
        strict=True)}

    print(f"  {'strategy':22} {'chunks':>7} {'med tok':>8} {'doc hit':>8} {'chunk hit':>10} "
          f"{'noise':>6} {'tok/q':>6} {'leak':>5} {'ingest':>9}")
    print("  " + "-" * 94)

    top_k = settings.default_top_k
    floor = settings.default_min_score
    for label, data in results.items():
        corpus, vectors = data["corpus"], data["vectors"]

        # Bound as defaults: these close over loop variables, and while each call happens
        # inside the same iteration today, a late-binding closure in a measurement script is
        # how a benchmark quietly reports one strategy's numbers under another's name.
        def ranked(vector, corpus=corpus, vectors=vectors):
            scores = vectors @ vector
            order = sorted(range(len(corpus)), key=lambda i: -scores[i])
            return [(corpus[i][0], corpus[i][1], float(scores[i])) for i in order[:top_k]
                    if scores[i] >= floor]

        doc_hits = chunk_hits = chunk_total = noise = chars = 0
        for question, want, expect_text in cases:
            kept = ranked(qvecs[question])
            doc_hits += any(fn == want for fn, _t, _s in kept)
            noise += sum(1 for fn, _t, _s in kept if fn != want)
            chars += sum(len(t) for _fn, t, _s in kept)
            if expect_text:
                chunk_total += 1
                chunk_hits += any(expect_text.lower() in t.lower() for _fn, t, _s in kept)
        leaked = sum(len(ranked(uvecs[q])) for q in unanswerable)

        sizes = sorted(data["sizes"])
        median = sizes[len(sizes) // 2] if sizes else 0
        ingest = (data["chunk_ms"] + data["embed_ms"]) / 1000
        print(f"  {label:22} {len(corpus):>7} {median:>8} "
              f"{f'{doc_hits}/{len(cases)}':>8} "
              f"{(f'{chunk_hits}/{chunk_total}' if chunk_total else '-'):>10} "
              f"{noise:>6} {chars // 4 // len(cases):>6} {leaked:>5} {ingest:>8.1f}s")

    print("\n  chunk-size distribution (tokens):")
    for label, data in results.items():
        sizes = sorted(data["sizes"])
        if not sizes:
            continue
        def q(fraction, sizes=sizes):
            return sizes[min(len(sizes) - 1, int(len(sizes) * fraction))]
        print(f"    {label:22} min {sizes[0]:>4}  p25 {q(.25):>4}  median {q(.5):>4}  "
              f"p75 {q(.75):>4}  max {sizes[-1]:>4}")

    print("\n  per-question document choice, where the two disagree:")
    header = "".join(f"{label[:20]:>22}" for label in results)
    print(f"    {'question':40}{header}")
    for question, want, _c in cases:
        picks = []
        for data in results.values():
            scores = data["vectors"] @ qvecs[question]
            best = max(range(len(data["corpus"])), key=lambda i: scores[i])
            picks.append(data["corpus"][best][0])
        if len(set(picks)) > 1:
            print(f"    {question[:40]:40}" + "".join(f"{p[:20]:>22}" for p in picks))
            print(f"    {'':40}{'want: ' + want[:20]:>22}")


if __name__ == "__main__":
    main()
