"""Day 18b: four candidate fixes for a retrieval failure, three of them rejected.

WHAT THIS IS EVIDENCE FOR. A user reported that the cloud model "worked before and crashes
now". It had not changed — `generation.py` was last modified five days earlier — and it had
not crashed. Asked "WHAT IS THE ADMISSION POLICY", the one chunk describing the admission
process ranked 7th at 0.588, under a 0.60 floor and outside a top_k of 5. The model was
handed a refunds table and two page headers and correctly reported that they did not answer
the question. A retrieval failure is indistinguishable, from the outside, from a broken model.

THE POINT OF KEEPING THIS SCRIPT IS THE REJECTIONS. The fix that shipped is small, and the
reason it is small is that three more obvious ones were measured first and were worse:

    moving the floor       cannot work in principle: the SAME floor was measured as too low
                           two days earlier (BACKLOG 20, noise at 0.6144 under a top of
                           0.6238) and is too high here by 0.012
    a relative floor       noise sits at 0.985 of its top hit, the wanted chunk at 0.862 of
                           its own — no ratio separates them
    a cross-encoder        ms-marco-MiniLM-L-6-v2 over 20 candidates moved the wanted chunk
                           from rank 7 to rank 8 and cost 2.1s per question
    smaller chunks         re-chunking the corpus at 256/192/128 tokens, with the floor
                           re-calibrated for each, scored 8/10, 7/10 and 7/10 against 9/10

Without this record the next person to read "top_k=7" will assume nobody tried a reranker.

    ./.venv/bin/python benchmarks/26_retrieval_gate.py

Retrieval only — no generation, no quota, and no writes. Needs the corpus in Postgres.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from app.config import settings  # noqa: E402
from app.retrieval import rank_rows  # noqa: E402

GOLDEN = ROOT / "evaluation" / "golden_questions.json"
SQL = """
SELECT c.id, c.document_id, c.text, -(c.embedding <#> %(q)s::vector) AS score,
       d.filename
FROM document_chunks c JOIN documents d ON d.id = c.document_id
ORDER BY c.embedding <#> %(q)s::vector LIMIT 40
"""


def main() -> None:
    questions = json.loads(GOLDEN.read_text())["questions"]
    model = SentenceTransformer(
        settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")

    print(f"{len(questions)} questions, floor {settings.default_min_score}, "
          f"top_k {settings.default_top_k}, anchor {settings.anchor_min_score}\n")
    print(f"{'question':24} {'policy':>10} {'target':>7} {'noise':>6} {'expanded':>9}")
    print("-" * 62)

    totals = {"plain": [0, 0], "anchored": [0, 0]}
    with psycopg.connect(settings.dsn) as conn:
        for q in questions:
            vector = model.encode(
                [settings.query_prefix + q["question"]], normalize_embeddings=True)[0]
            literal = "[" + ",".join(repr(float(v)) for v in vector) + "]"
            raw = conn.execute(SQL, {"q": literal}).fetchall()
            names = {str(r[0]): r[4] for r in raw}
            rows = [(r[0], r[1], r[2], r[3]) for r in raw]

            for policy, anchor in (("plain", None), ("anchored", settings.anchor_min_score)):
                kept, texts, _c, _d, expanded = rank_rows(
                    rows, settings.default_top_k, settings.default_min_score, anchor)
                if q["answerable"]:
                    # `expect_chunk_contains` where it exists, because the looser
                    # `expect_answer_contains` is not safe here: "admission" appears in the
                    # repeated page HEADER of five prospectus chunks, so the first version
                    # of this script scored both policies 12/12 and hid the very difference
                    # it was written to measure.
                    exact = q.get("expect_chunk_contains")
                    want = q.get("expect_answer_contains", [])
                    hit = any(
                        names[str(c.chunk_id)] == q.get("expect_document")
                        and (exact in t if exact
                             else any(w.lower() in t.lower() for w in want))
                        for c, t in zip(kept, texts, strict=False))
                    noise = sum(1 for c in kept
                                if names[str(c.chunk_id)] != q.get("expect_document"))
                    totals[policy][0] += hit
                    totals[policy][1] += noise
                else:
                    hit, noise = not kept, len(kept)   # an unanswerable "hit" is silence
                    totals[policy][0] += hit
                    totals[policy][1] += noise
                print(f"{q['id'][:24]:24} {policy:>10} {'yes' if hit else 'NO':>7} "
                      f"{noise:>6} {expanded:>9}")
        print()
        for policy, (hits, noise) in totals.items():
            print(f"  {policy:9} {hits}/{len(questions)} correct, {noise} off-document chunks")


if __name__ == "__main__":
    main()
