"""Day 19: is a bigger embedder worth it? Measured before anything is migrated.

THE ASK was "try the better embedder". The obvious move is to pick bge-base, write a
migration, re-embed and see. That is the expensive order. The column is `vector(384)`, so a
768-dimension model cannot be queried through Postgres at all until a migration exists —
and a migration is forward-only. Deciding FIRST costs one download and three minutes.

So this compares candidates ENTIRELY IN MEMORY: the chunk text comes from Postgres, each
model embeds it here, and similarity is a dot product over normalised vectors — which is
exactly what `<#>` computes against the stored column. Same arithmetic, no schema change.

THREE THINGS THAT WOULD MAKE THE COMPARISON A LIE, and what is done about each:

1. COMPARING A TUNED MODEL AGAINST AN UNTUNED ONE. `default_min_score = 0.55` was swept
   against bge-small's score distribution (benchmarks/27). A different model puts its scores
   somewhere else entirely; judging it at 0.55 measures the threshold, not the model. Every
   candidate here is swept over the same floor range and reported at ITS OWN best floor.

2. THE WRONG PREFIX. bge wants "Represent this sentence for searching relevant passages: "
   on the QUERY only; e5 wants "query: " and "passage: " on both sides; gte wants neither.
   Feeding a model the wrong convention costs it real accuracy, and the harness would be
   reporting its own mistake as the model's. The prefixes are per-model below.

3. JUDGING ON HITS ALONE. Both candidates will likely retrieve the right document for
   almost everything — bge-small already does 9/9. Hits are not where this corpus hurts.

WHAT ACTUALLY DECIDES IT IS HEADROOM. The floor is a single number separating "answer this"
from "say you cannot". It only works if there is a GAP between the worst answerable question
and the best unanswerable one. On bge-small that gap is effectively zero:

    what is university policy   0.5926   answerable
    Follow up on finance        0.5925   off topic

One ten-thousandth apart. No floor can separate those, which is the entire reason the
document-margin guard had to be built. A 768-dimension model costs double the storage and
roughly triple the query encode time; it earns that only if it pulls those two apart.

    ./.venv/bin/python benchmarks/28_embedder_comparison.py
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import psycopg  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from app.config import settings  # noqa: E402

GOLDEN = ROOT / "evaluation" / "golden_questions.json"

BGE_QUERY = "Represent this sentence for searching relevant passages: "

# (name, query prefix, passage prefix). Revisions are resolved and PRINTED rather than
# pinned: a benchmark that pins a revision it has not yet chosen is pinning a guess. The
# resolved SHA is the one that goes into config.py if a candidate wins.
CANDIDATES = [
    ("BAAI/bge-small-en-v1.5", BGE_QUERY, ""),   # incumbent, 384 — also validates the harness
    ("BAAI/bge-base-en-v1.5", BGE_QUERY, ""),    # 768, same family and prefix convention
    ("intfloat/e5-base-v2", "query: ", "passage: "),  # 768, different family: a control
]
# NOT TESTED: Alibaba-NLP/gte-base-en-v1.5. It requires trust_remote_code=True, which
# executes Python downloaded from the model repo inside this service. That is a supply-chain
# decision, not a retrieval one, and it is not mine to make quietly in a benchmark.

# Questions a real user typed that failed here. Each one appears in a complaint.
REPORTED = [
    ("what is university policy", "University_Admission_Prospectus_2027.pdf"),
    ("WHAT IS THE ADMISSION POLICY", "University_Admission_Prospectus_2027.pdf"),
    ("what is the admission process?", "University_Admission_Prospectus_2027.pdf"),
    ("tell me about ai safety", "AI_safety.pdf"),
    ("summarise abstract of ai-safety research paper", "AI_safety.pdf"),
]

# The named collision, from benchmarks/27. Both labels are known: the first is answerable
# from the prospectus, the second is a task follow-up with no answer in the corpus. Their
# gap under bge-small is 0.0001. This is the single number the upgrade has to move.
COLLISION = ("what is university policy", "Follow up on finance")

# Off-topic probes that SHARE CORPUS VOCABULARY — the pressure the golden unanswerable set
# does not apply. "What is the capital of France?" scores 0.44 against an aviation deck;
# these do not, because every content word in them appears somewhere in the corpus.
#
# EACH LABEL WAS CHECKED AGAINST THE CORPUS TEXT, and the first draft of this list got one
# wrong: "what is the tuition refund policy" scored 0.8124 and looked like a catastrophic
# leak, until grepping the chunks found the prospectus carries an explicit HEC refund
# schedule — "100% of tuition up to the 7th day of classes". The question was ANSWERABLE and
# 0.8124 was correct retrieval. It is removed rather than kept, because a mislabelled probe
# does not overstate the danger, it invents one.
#
# The four below were confirmed absent: no chunk contains "maintenance schedule", none
# contains "aviation safety board" or "chair", the prospectus is the 2027 intake so no 2025
# admission count exists, and "Follow up on finance" is a task follow-up already shown in
# benchmarks/27 to have no answer here.
PROBES = [
    "Follow up on finance",
    "what is the maintenance schedule for Q4",
    "how many students were admitted in 2025",
    "who chairs the aviation safety board",
]


def collapse(pairs):
    """Drop byte-identical text, as rank_rows does before anything else."""
    seen, out = set(), []
    for fn, body, score in pairs:
        if body in seen:
            continue
        seen.add(body)
        out.append((fn, body, score))
    return out


def main() -> None:
    golden = json.loads(GOLDEN.read_text())["questions"]
    answerable = [(q["question"], q["expect_document"]) for q in golden if q["answerable"]]
    unanswerable = [q["question"] for q in golden if not q["answerable"]]
    everything = answerable + REPORTED

    with psycopg.connect(settings.dsn) as conn:
        corpus = conn.execute(
            "SELECT d.filename, c.text FROM document_chunks c "
            "JOIN documents d ON d.id = c.document_id ORDER BY d.filename, c.ordinal"
        ).fetchall()
    print(f"\n  {len(corpus)} chunks, "
          f"{len({fn for fn, _ in corpus})} documents, "
          f"{len(answerable)} golden answerable, {len(REPORTED)} reported, "
          f"{len(unanswerable)} golden unanswerable, {len(PROBES)} probes\n")

    queries = [q for q, _ in everything] + unanswerable + PROBES
    results = {}

    for name, qp, pp in CANDIDATES:
        model = SentenceTransformer(name, device="cpu")
        dim = model.get_sentence_embedding_dimension()

        passages = model.encode([pp + text for _fn, text in corpus],
                                normalize_embeddings=True, batch_size=16)
        t0 = time.perf_counter()
        qvecs = model.encode([qp + q for q in queries], normalize_embeddings=True)
        encode_ms = (time.perf_counter() - t0) * 1000 / len(queries)

        scores = qvecs @ passages.T                       # == -(embedding <#> query)
        ranked = {}
        for i, q in enumerate(queries):
            order = np.argsort(-scores[i])[:40]
            ranked[q] = collapse([(corpus[j][0], corpus[j][1], float(scores[i][j]))
                                  for j in order])
        results[name] = (dim, encode_ms, ranked)
        del model

        print(f"  {name}   {dim} dims   {encode_ms:.0f} ms/query encode")
        print(f"    {'floor':>6} {'golden':>8} {'reported':>9} {'LEAKED':>7} {'noise':>7}")
        print("    " + "-" * 44)
        best = None
        for floor in [round(0.30 + i * 0.01, 2) for i in range(46)]:
            g = sum(any(fn == want for fn, _b, s in ranked[q][:settings.default_top_k]
                        if s >= floor) for q, want in answerable)
            r = sum(any(fn == want for fn, _b, s in ranked[q][:settings.default_top_k]
                        if s >= floor) for q, want in REPORTED)
            leaked = sum(len([1 for _f, _b, s in ranked[q][:settings.default_top_k]
                              if s >= floor]) for q in unanswerable)
            noise = sum(len([1 for fn, _b, s in ranked[q][:settings.default_top_k]
                             if s >= floor and fn != want]) for q, want in everything)
            # Best = everything retrieved, nothing leaked, least noise. Lowest such floor
            # loses to a higher one only on noise, so prefer the higher floor at equal noise.
            if g == len(answerable) and r == len(REPORTED) and leaked == 0:
                if best is None or noise <= best[3]:
                    best = (floor, g, r, noise)
            if floor in (0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
                print(f"    {floor:>6.2f} {f'{g}/{len(answerable)}':>8} "
                      f"{f'{r}/{len(REPORTED)}':>9} {leaked:>7} {noise:>7}")

        if best:
            print(f"    best floor {best[0]:.2f}: {best[1]}/{len(answerable)} golden, "
                  f"{best[2]}/{len(REPORTED)} reported, 0 leaked, {best[3]} noise chunks")
        else:
            print("    NO floor retrieves everything without leaking")

        # HEADROOM, the number that decides the upgrade.
        worst_ok = min(ranked[q][0][2] for q, _w in everything)
        best_bad = max(ranked[q][0][2] for q in unanswerable)
        print(f"    headroom (verified labels)  {worst_ok - best_bad:+.4f}   "
              f"worst answerable {worst_ok:.4f} vs best unanswerable {best_bad:.4f}")

        best_probe = max(ranked[q][0][2] for q in PROBES)
        print(f"    headroom vs probes          {worst_ok - best_probe:+.4f}   "
              f"highest probe {best_probe:.4f}")

        a, b = COLLISION
        print(f"    the collision               {ranked[a][0][2] - ranked[b][0][2]:+.4f}   "
              f"'{a}' {ranked[a][0][2]:.4f} vs '{b}' {ranked[b][0][2]:.4f}\n")

    print("  probe scores per model (pressure on the floor):")
    header = "".join(f"{n.split('/')[-1][:18]:>20}" for n, _q, _p in CANDIDATES)
    print(f"    {'probe':40}{header}")
    for p in PROBES:
        row = "".join(f"{results[n][2][p][0][2]:>20.4f}" for n, _q, _p in CANDIDATES)
        print(f"    {p[:40]:40}{row}")


if __name__ == "__main__":
    main()
