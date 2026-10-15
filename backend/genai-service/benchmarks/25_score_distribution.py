"""Day 18: is the 0.60 floor still placing the line in the right spot?

OBSERVABILITY'S JOB IS TO MAKE A PROBLEM VISIBLE AND QUANTIFIED. This script does not change
the threshold. A measured value should not be re-placed as a side effect of a logging day;
it should be re-placed on evidence, deliberately, and this is the evidence.

WHAT PROMPTED IT, straight off a live trace the user was reading:

    describe the refund and revision rules in detail
      rank 1  0.6238  University_Admission_Prospectus_2027.pdf  p4   <- the refund rules
      rank 2  0.6144  Junior_Fullstack_GenAI_Training_Tracker.xlsx    <- product backlog
      rank 3  0.6071  Junior_Fullstack_GenAI_Training_Tracker.xlsx    <- review rubric
      rank 4  0.6020  AeroTwin_Defense_Prep.pdf  p15                  <- a demo script
      rank 5  0.6020  AI_Assessment_...graded.csv                     <- a marking sheet

Four of five chunks are unrelated to the question, every one of them scraping over the floor
by two hundredths. They cost 2,325 prompt tokens and 45.9 seconds of decode.

WHY THIS WAS NOT TRUE WHEN THE FLOOR WAS SET. Day 6 calibrated 0.60 against a corpus that was
small and 2.72x duplicated. The corpus is now 14 documents of genuinely unrelated material —
a prospectus, a training tracker, an aviation deck, a marking spreadsheet — and a floor
chosen when almost everything was about one subject admits almost anything when it is not.

WHAT IS MEASURED. For each golden question, the gap between the top score and the rest, and
how far the pack sits above the floor. A corpus where relevance separates cleanly shows a
visible step after rank 1; one where the floor is too low shows a flat run of near-identical
scores, which is exactly what a trace full of noise looks like from the inside.

    ./.venv/bin/python benchmarks/25_score_distribution.py

Retrieval only — no generation, no quota, and fast.
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import psycopg  # noqa: E402

from app.config import settings  # noqa: E402

OWNER_EMAIL = "mayub@nisum.com"
BASE = "http://127.0.0.1:8000"
GOLDEN = ROOT / "evaluation" / "golden_questions.json"


def corpus():
    with psycopg.connect(settings.dsn) as conn:
        owner = conn.execute("select id from users where email=%s", (OWNER_EMAIL,)).fetchone()
        if owner is None:
            raise SystemExit(f"no user {OWNER_EMAIL}")
        documents = [str(r[0]) for r in conn.execute(
            "select id from documents where owner_id=%s and status='ready'", (owner[0],)).fetchall()]
        names = {str(i): f for i, f in conn.execute(
            "select c.id, d.filename from document_chunks c join documents d on d.id=c.document_id"
        ).fetchall()}
    return documents, names


def retrieve(question: str, documents: list[str], min_score: float):
    """/retrieve, never /answer: this measures the floor, and generation would only add
    45 seconds per question and a dependency on the model behaving."""
    response = httpx.post(f"{BASE}/retrieve", timeout=120, json={
        "question": question, "allowed_document_ids": documents,
        "top_k": 10, "min_score": min_score})
    response.raise_for_status()
    return response.json()["retrieved"]


def main() -> None:
    documents, names = corpus()
    questions = [q for q in json.loads(GOLDEN.read_text())["questions"] if q.get("answerable")]
    print(f"corpus: {len(documents)} documents   questions: {len(questions)}   "
          f"floor: {settings.default_min_score}\n")

    print(f"{'question':<42}{'top':>7}{'2nd':>7}{'gap':>7}{'over floor':>11}  documents")
    print("-" * 104)

    gaps, spreads, admitted = [], [], []
    for q in questions:
        rows = retrieve(q["question"], documents, settings.default_min_score)
        if not rows:
            print(f"{q['question'][:40]:<42}{'— nothing cleared the floor':>40}")
            continue
        scores = [r["score"] for r in rows]
        top = scores[0]
        second = scores[1] if len(scores) > 1 else float("nan")
        gap = top - second if len(scores) > 1 else float("nan")
        distinct_docs = len({names.get(r["chunk_id"], "?") for r in rows})

        gaps.append(gap if gap == gap else 0.0)
        spreads.append(top - scores[-1])
        admitted.append(len(scores))
        print(f"{q['question'][:40]:<42}{top:>7.4f}{second:>7.4f}{gap:>7.4f}"
              f"{top - settings.default_min_score:>11.4f}  {distinct_docs} distinct")

    print()
    print("  WHAT THESE NUMBERS MEAN")
    print("  A LARGE gap between rank 1 and rank 2 means relevance separates cleanly and the")
    print("  floor is doing real work. A SMALL gap with many chunks admitted means the floor")
    print("  is below the noise and the model is being handed filler to read.")
    print()
    print(f"  median rank1-rank2 gap     : {statistics.median(gaps):.4f}")
    print(f"  median top-to-last spread  : {statistics.median(spreads):.4f}")
    print(f"  median chunks admitted     : {statistics.median(admitted):.0f} (of top_k=10)")
    print(f"  questions where the gap is under 0.02 : "
          f"{sum(1 for g in gaps if g < 0.02)}/{len(gaps)}")

    print("\n  SWEEPING THE FLOOR — how many chunks survive at each threshold")
    print(f"  {'floor':<8}{'median admitted':>17}{'questions with 0':>19}")
    for floor in (0.60, 0.62, 0.64, 0.66, 0.68, 0.70):
        counts = [len(retrieve(q["question"], documents, floor)) for q in questions]
        print(f"  {floor:<8.2f}{statistics.median(counts):>17.0f}{sum(1 for c in counts if c == 0):>19}")

    print("\n  NOT CHANGED. Raising the floor trades noise for silence, and `insufficient_context`")
    print("  on an answerable question is the worse failure — Day 6 set 0.60 for that reason.")
    print("  The right fix may not be the threshold at all: a repeated PDF page header appears")
    print("  in five of eight prospectus chunks (BACKLOG 17) and inflates every score it is in.")


if __name__ == "__main__":
    main()
