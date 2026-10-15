"""Day 11b: is the answer actually made of the context, or of the model's training?

The failure this measures was found in the UI, not in a benchmark. Asked "tell me about how
to defend fyp", retrieval returned ONE chunk at 0.603 — a table of contents — the outcome
was declared `grounded` because a chunk cleared the threshold, and the model then answered
from parametric memory, inventing "FYP = Flexible Workplace Policy". Zero citations, zero
dropped quotes, and a confident wrong answer on screen with no source.

`grounded` is decided by RETRIEVAL scores before the model runs. Nothing afterwards checks
that the answer used what it was given. This measures a check that can: what fraction of the
answer's content words appear anywhere in the context it was shown.

It is deliberately not a model call. A second model judging the first is another 0.5B
opinion, and Day 10 measured what those are worth.
"""
import psycopg
import requests

from app.config import settings
from app.prompts.parsing import _words

OWNER = "83814a60-6bd4-427a-8382-8972debaa6ca"

QUESTIONS = [
    "What does the AeroTwin document say about the demo?",
    "What is covered in the GenAI training tracker?",
    "what are the formulas of adbms",
    "what is the fleet size",
    # The one that started this: retrieval clears the threshold on a table of contents.
    "tell me about how to defend fyp",
]


def overlap(answer: str, chunks: list[str]) -> float:
    answer_words = set(_words(answer))
    if not answer_words:
        return 0.0
    context_words: set[str] = set()
    for chunk in chunks:
        context_words |= set(_words(chunk))
    return len(answer_words & context_words) / len(answer_words)


with psycopg.connect(settings.dsn) as conn:
    allowed = [str(r[0]) for r in conn.execute(
        "select id from documents where owner_id=%s", (OWNER,)).fetchall()]

    print(f"{'question':<46}{'cites':>6}{'drops':>7}{'overlap':>9}  verdict")
    print("-" * 92)
    for question in QUESTIONS:
        body = {"question": question, "allowed_document_ids": allowed}
        answer = requests.post("http://127.0.0.1:8000/answer", json=body, timeout=300).json()
        if "detail" in answer:
            print(f"{question[:44]:<46}  ERROR {answer['detail'].get('code')}")
            continue

        trace = answer["trace"]
        chunks = []
        for r in trace["retrieved"]:
            # A cited chunk can be gone: V19 made citations survive re-ingestion by design.
            row = conn.execute("select text from document_chunks where id=%s", (r["chunk_id"],)).fetchone()
            if row is not None:
                chunks.append(row[0])
        score = overlap(answer["answer"], chunks) if chunks else 0.0
        verdict = "made of the context" if score >= 0.5 else "NOT made of the context"
        print(f"{question[:44]:<46}{len(answer['citations']):>6}{len(trace['dropped_quotes']):>7}"
              f"{score:>9.3f}  {verdict}")
