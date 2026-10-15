"""Day 13: the golden set. Known questions, known sources, two backends.

Four thresholds in this system were set on tiny samples and are still provisional:
min_score (n=2), the citation confidence band (n=2), the grounding floor (n=4/1) and the
token cap. This is the instrument that is supposed to replace those guesses, and the first
thing it does is compare the local model against Gemini on identical retrieval.

WHAT IS MEASURED, and why each is separate:

  retrieval   did the expected document come back at all?   -> bge's job
  citation    was the expected document the one cited?      -> quote resolution's job
  answer      does the answer contain what it must?         -> the generator's job

Keeping them apart is the point. Day 6 through Day 12 kept finding that retrieval was
right and generation was wrong, and a single "accuracy" number would have hidden that
every time.

    PYTHONPATH=$PWD ./.venv/bin/python benchmarks/21_golden_set.py            # both
    PYTHONPATH=$PWD ./.venv/bin/python benchmarks/21_golden_set.py local      # one
"""
import json
import sys
import time
from pathlib import Path

import psycopg
import requests

from app.config import settings

OWNER = "83814a60-6bd4-427a-8382-8972debaa6ca"
BASE = "http://127.0.0.1:8000"
GOLDEN = Path(__file__).resolve().parents[1] / "evaluation" / "golden_questions.json"


def documents_for(conn, document_ids):
    """chunk_id -> filename, so a citation can be checked against an expected document."""
    rows = conn.execute(
        "select c.id, d.filename from document_chunks c join documents d on d.id = c.document_id "
        "where c.document_id = ANY(%s::uuid[])", (document_ids,)).fetchall()
    return {str(chunk_id): filename for chunk_id, filename in rows}


def evaluate(backend: str, questions, allowed, chunk_to_file):
    print(f"\n{'=' * 104}\n  BACKEND: {backend}\n{'=' * 104}")
    print(f"{'question':<46}{'retr':>6}{'cite':>6}{'ans':>5}{'secs':>7}  answer")
    print("-" * 104)

    scores = {"retrieval": 0, "citation": 0, "answer": 0, "answerable": 0,
              "refused_correctly": 0, "unanswerable": 0, "seconds": 0.0}

    for q in questions:
        body = {"question": q["question"], "allowed_document_ids": allowed}
        if backend:
            body["model"] = backend
        started = time.perf_counter()
        try:
            response = requests.post(f"{BASE}/answer", json=body, timeout=300).json()
        except Exception as failure:
            print(f"{q['id'][:44]:<46}  REQUEST FAILED {type(failure).__name__}")
            continue
        seconds = time.perf_counter() - started
        scores["seconds"] += seconds

        if "detail" in response:
            print(f"{q['id'][:44]:<46}  ERROR {response['detail'].get('message','')[:40]}")
            continue

        answer = response["answer"] or ""
        cited_files = {chunk_to_file.get(c["chunk_id"], "?") for c in response["citations"]}
        retrieved_files = {chunk_to_file.get(r["chunk_id"], "?") for r in response["trace"]["retrieved"]}

        if q["answerable"]:
            scores["answerable"] += 1
            retrieval_hit = q["expect_document"] in retrieved_files
            citation_hit = q["expect_document"] in cited_files
            answer_hit = all(fragment.lower() in answer.lower()
                             for fragment in q["expect_answer_contains"])
            scores["retrieval"] += retrieval_hit
            scores["citation"] += citation_hit
            scores["answer"] += answer_hit
            marks = (f"{'Y' if retrieval_hit else '.':>6}{'Y' if citation_hit else '.':>6}"
                     f"{'Y' if answer_hit else '.':>5}")
        else:
            scores["unanswerable"] += 1
            # Refusing correctly means producing NO answer — insufficient_context, or an
            # answer withheld by the grounding guard. Either is the system declining.
            refused = response["outcome"] == "insufficient_context" or not answer.strip()
            scores["refused_correctly"] += refused
            marks = f"{'—':>6}{'—':>6}{'Y' if refused else 'NO':>5}"

        print(f"{q['id'][:44]:<46}{marks}{seconds:>7.1f}  {answer[:36]!r}")

    n_ans, n_un = scores["answerable"], scores["unanswerable"]
    print(f"\n  retrieval found the right document : {scores['retrieval']}/{n_ans}")
    print(f"  cited the right document           : {scores['citation']}/{n_ans}")
    print(f"  answer contained what it must      : {scores['answer']}/{n_ans}")
    print(f"  correctly refused the unanswerable : {scores['refused_correctly']}/{n_un}")
    print(f"  mean latency                       : {scores['seconds'] / max(len(questions), 1):.1f}s")
    return scores


def main() -> None:
    backends = sys.argv[1:] or ["local", "gemini"]
    questions = json.loads(GOLDEN.read_text())["questions"]

    with psycopg.connect(settings.dsn) as conn:
        allowed = [str(r[0]) for r in conn.execute(
            "select id from documents where owner_id = %s", (OWNER,)).fetchall()]
        chunk_to_file = documents_for(conn, allowed)

    print(f"  {len(questions)} questions, {sum(q['answerable'] for q in questions)} answerable, "
          f"{len(allowed)} documents in scope")
    results = {b: evaluate(b, questions, allowed, chunk_to_file) for b in backends}

    if len(results) > 1:
        n_ans = next(iter(results.values()))["answerable"]
        n_un = next(iter(results.values()))["unanswerable"]
        print(f"\n{'=' * 104}\n  SIDE BY SIDE\n{'=' * 104}")
        print(f"{'':<16}{'retrieval':>12}{'citation':>11}{'answer':>9}{'refusal':>10}{'mean secs':>12}")
        for backend, s in results.items():
            print(f"  {backend:<14}{s['retrieval']}/{n_ans:<10}{s['citation']}/{n_ans:<9}"
                  f"{s['answer']}/{n_ans:<7}{s['refused_correctly']}/{n_un:<8}"
                  f"{s['seconds'] / len(questions):>11.1f}")
        print("\n  Retrieval is identical by construction — same embeddings, same chunks, same")
        print("  threshold. Any difference in the other columns is the generator alone.")


if __name__ == "__main__":
    main()
