"""Day 16: how often does a citation survive, and does the answer-derived fallback help?

THE DEFECT THIS MEASURES, found by a user in the UI rather than by a test. Under qa-v2 the
model must return {"answer": ..., "quotes": [...]} and citations are resolved FROM those
quotes — never from numbers the model invents. Qwen2.5-0.5B keeps to that envelope on short
factual questions and ABANDONS IT on open-ended ones, answering in plain prose. There are
then no quotes to resolve, so a well-grounded answer ships with zero sources:

    "what is the refund policy"        parse_path=json           1 citation   overlap 0.90
    "Tell me about admission policy"   parse_path=text_fallback  0 citations  overlap 0.73

Note the overlap. The second answer IS made of the documents — the evidence exists and is
simply unused, because the model did not label it.

Day 7 measured qa-v2 parsing 10/10 and wrote down that "ten samples of one question is not
proof". This is the counterexample, and this script is the proof that was missing: the same
questions, split by SHAPE, against both backends.

HOW THE A/B IS KEPT HONEST. Each question is generated ONCE, with include_raw=true, and
both strategies are then computed from that identical reply — quote-derived first, and the
answer-derived fallback only where that produced nothing. Running the suite twice against
two builds would compare two different model outputs, and a 0.5B model asked the same
open-ended question twice does not answer the same way. One generation, two numbers.

    ./.venv/bin/python benchmarks/24_citation_recovery.py              # local
    ./.venv/bin/python benchmarks/24_citation_recovery.py --gemini     # costs quota
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402

from app.config import settings  # noqa: E402
from app.prompts import cite_from_answer, parse_quoted_answer  # noqa: E402

OWNER_EMAIL = "mayub@nisum.com"
BASE = "http://127.0.0.1:8000"

#: Split by SHAPE, because shape is what the failure correlates with. Short/factual answers
#: fit the envelope; open-ended ones invite prose and the 0.5B model stops emitting JSON.
#: These are questions a user would actually type, not phrasings chosen to make a point.
QUESTIONS = [
    ("factual", "what is the refund policy"),
    ("factual", "how much of the tuition is refunded in the first week"),
    ("factual", "is the admission fee refundable"),
    ("factual", "what happens if information is false"),
    ("factual", "how are fees paid"),
    ("open", "Tell me about admission policy"),
    ("open", "explain the admission process"),
    ("open", "summarise the fee structure"),
    ("open", "what should an applicant know before applying"),
    ("open", "describe the refund and revision rules in detail"),
]


def allowed_documents() -> list[str]:
    with psycopg.connect(settings.dsn) as conn:
        owner = conn.execute("select id from users where email=%s", (OWNER_EMAIL,)).fetchone()
        if owner is None:
            raise SystemExit(f"no user {OWNER_EMAIL}; this benchmark reads the real corpus")
        rows = conn.execute(
            "select id from documents where owner_id=%s and status='ready'", (owner[0],)
        ).fetchall()
    return [str(r[0]) for r in rows]


def wait_until_ready(timeout_s: int = 180) -> None:
    """Block until the service can answer.

    Not defensive padding. This benchmark runs against a DEV server, which is normally
    started with --reload: any edit anywhere in the tree restarts it, and the two models
    take ~45s to come back. A run that started before an edit and 503s after one has
    measured nothing, and the traceback looks like a product failure rather than a
    reload — which is precisely the confidently-wrong signal this project keeps finding.
    """
    import httpx

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/health/ready", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        print("  (service reloading — waiting)", flush=True)
        time.sleep(5)
    raise SystemExit(f"the service was not ready within {timeout_s}s")


def ask(question: str, documents: list[str], backend: str) -> dict:
    import httpx

    wait_until_ready()
    response = httpx.post(
        f"{BASE}/answer",
        json={"question": question, "allowed_document_ids": documents, "model": backend,
              # The verbatim reply is what makes the A/B possible: both strategies are
              # computed from it, so the comparison is not confounded by the model
              # answering differently on a second run.
              "include_raw": True},
        timeout=600,
    )
    if response.status_code == 503:
        # Reloaded between the readiness check and the request. One retry, after waiting.
        wait_until_ready()
        response = httpx.post(
            f"{BASE}/answer",
            json={"question": question, "allowed_document_ids": documents, "model": backend,
                  "include_raw": True},
            timeout=600,
        )
    response.raise_for_status()
    return response.json()


def chunk_texts_for(trace: dict) -> list[str]:
    """The texts the service actually showed the model, in rank order.

    Read from Postgres by chunk id rather than echoed back by the service — the same rows
    retrieval used, and the ordinals in a quote resolution index into THIS list.
    """
    ids = [c["chunk_id"] for c in trace["retrieved"]]
    if not ids:
        return []
    with psycopg.connect(settings.dsn) as conn:
        rows = dict(conn.execute(
            "select id::text, text from document_chunks where id = ANY(%s::uuid[])", (ids,)
        ).fetchall())
    return [rows[i] for i in ids if i in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gemini", action="store_true",
                    help="measure the cloud backend too. Costs daily free quota")
    args = ap.parse_args()

    documents = allowed_documents()
    backends = ["local"] + (["gemini"] if args.gemini else [])
    print(f"corpus: {len(documents)} ready documents   backends: {backends}\n")

    for backend in backends:
        print(f"{'shape':<9}{'question':<50}{'parse path':<16}{'BEFORE':>7}{'AFTER':>7}"
              f"{'overlap':>9}  {'source':<16}{'time':>5}")
        print("-" * 120)
        rows = []
        for shape, question in QUESTIONS:
            started = time.perf_counter()
            body = ask(question, documents, backend)
            trace = body["trace"]
            texts = chunk_texts_for(trace)
            raw = trace["raw_model_reply"] or ""

            # BEFORE — citations as qa-v2 derives them: from the model's declared quotes.
            parsed = parse_quoted_answer(raw, texts)
            before = len(parsed.cited)

            # AFTER — the fallback, which runs only where the above produced nothing.
            if parsed.cited or not parsed.answer.strip():
                after, source = before, ("quotes" if before else "none")
            else:
                recovered, _ = cite_from_answer(parsed.answer, texts)
                after = len(recovered)
                source = "answer_fallback" if recovered else "none"

            # WITHHELD ANSWERS COUNT AS NOTHING, and getting this wrong was a real error in
            # the first version of this script. An answer below the grounding floor is
            # suppressed by the service — the user is shown the insufficient-context
            # sentence instead — so whatever citations its raw text would have produced are
            # never seen by anyone. Counting them measured the parser, not the product, and
            # inflated BOTH columns. Three of ten questions here are in that state.
            withheld = body["outcome"] != "grounded"
            if withheld:
                before = after = 0
                source = "withheld"

            rows.append((shape, before, after, source))
            flag = "  <- RECOVERED" if after > before else ("  <- withheld" if withheld else "")
            print(f"{shape:<9}{question[:48]:<50}{parsed.parse_path:<16}{before:>7}{after:>7}"
                  f"{trace['grounding_overlap']:>9.2f}  {source:<16}{time.perf_counter() - started:>4.0f}s{flag}")

        print()
        print(f"  {'':<9}{'answers with >=1 citation':<34}{'BEFORE':>8}{'AFTER':>8}")
        for shape in ("factual", "open"):
            group = [r for r in rows if r[0] == shape]
            print(f"  {shape:<9}{'':<34}{sum(1 for r in group if r[1] > 0):>5}/{len(group)}"
                  f"{sum(1 for r in group if r[2] > 0):>6}/{len(group)}")
        print(f"  {'OVERALL':<9}{'':<34}{sum(1 for r in rows if r[1] > 0):>5}/{len(rows)}"
              f"{sum(1 for r in rows if r[2] > 0):>6}/{len(rows)}")
        withheld = sum(1 for r in rows if r[3] == "withheld")
        print(f"\n  recovered by the fallback : {sum(1 for r in rows if r[3] == 'answer_fallback')}")
        print(f"  withheld as ungrounded    : {withheld}  (shown to nobody; not a citation failure)")
        shipped = [r for r in rows if r[3] != "withheld"]
        print(f"  of {len(shipped)} answers a user actually sees: "
              f"{sum(1 for r in shipped if r[1] > 0)} cited BEFORE, "
              f"{sum(1 for r in shipped if r[2] > 0)} AFTER")
        print()


if __name__ == "__main__":
    main()
