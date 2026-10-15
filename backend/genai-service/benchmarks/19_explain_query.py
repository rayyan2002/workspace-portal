"""Explain ONE live query, end to end, in a form a human can read.

Why this exists: the trace is thrown away. `/answer` returns every number needed to
diagnose an answer — what was retrieved, what it scored, what was collapsed, whether the
grounding guard nearly fired — and Spring consumes it, logs one line, and discards it.
Ask "why did that answer happen?" an hour later and nothing can tell you.

This re-runs a question against the running service and joins the trace back to Postgres,
so UUIDs become filenames, pages and text. It is the manual version of the observability
Day 18 owes, and it is deliberately read-only: it changes nothing and writes nothing.

    PYTHONPATH=$PWD ./.venv/bin/python benchmarks/19_explain_query.py "your question here"
    PYTHONPATH=$PWD ./.venv/bin/python benchmarks/19_explain_query.py "question" --retrieve-only
    PYTHONPATH=$PWD ./.venv/bin/python benchmarks/19_explain_query.py "question" --full-text
"""
import sys
import textwrap

import psycopg
import requests

from app.config import settings

OWNER_EMAIL = "mayub@nisum.com"
BASE = "http://127.0.0.1:8000"
RULE = "=" * 100


def h(title: str) -> None:
    print(f"\n{RULE}\n  {title}\n{RULE}")


def wrap(text: str, indent: str = "      ") -> str:
    return textwrap.fill(" ".join(text.split()), width=94,
                         initial_indent=indent, subsequent_indent=indent)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    retrieve_only = "--retrieve-only" in sys.argv
    full_text = "--full-text" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    question = args[0]

    with psycopg.connect(settings.dsn) as conn:
        owner = conn.execute("select id from users where email=%s", (OWNER_EMAIL,)).fetchone()
        if owner is None:
            print(f"no user {OWNER_EMAIL}")
            sys.exit(1)
        owner_id = owner[0]

        docs = conn.execute(
            "select id, filename from documents where owner_id=%s and status='ready' order by filename",
            (owner_id,)).fetchall()
        allowed = [str(d[0]) for d in docs]

        h("1. THE CORPUS THIS QUESTION MAY SEE")
        # count(*) always returns a row, but the driver's type says it may not.
        total_row = conn.execute(
            "select count(*) from document_chunks where document_id = ANY(%s::uuid[])",
            (allowed,)).fetchone()
        total_chunks = total_row[0] if total_row else 0
        print(f"  user                 : {OWNER_EMAIL}")
        print(f"  documents (ready)    : {len(docs)}")
        print(f"  chunks searchable    : {total_chunks}")
        print(f"  embedding model      : {settings.embedding_model} @ {settings.embedding_model_revision[:12]}")
        print(f"  vector dimensions    : {settings.embedding_dim}")
        print("\n  per document:")
        for doc_id, filename in docs:
            count_row = conn.execute(
                "select count(*) from document_chunks where document_id=%s", (doc_id,)).fetchone()
            n = count_row[0] if count_row else 0
            print(f"      {n:>4} chunks   {filename}")

        h("2. THE QUESTION, AND HOW IT IS TURNED INTO A SEARCH")
        print(f"  question             : {question!r}")
        print(f"  query prefix applied : {settings.query_prefix!r}")
        print(f"  top_k                : {settings.default_top_k}")
        print(f"  min_score            : {settings.default_min_score}   (cosine similarity floor)")
        print(f"  over-fetch           : top_k x {settings.overfetch_factor} before duplicate collapsing")

        body = {"question": question, "allowed_document_ids": allowed, "include_raw": True}
        endpoint = "/retrieve" if retrieve_only else "/answer"
        response = requests.post(f"{BASE}{endpoint}", json=body, timeout=300).json()

        if "detail" in response:
            print(f"\n  ERROR {response['detail'].get('code')}: {response['detail'].get('message')}")
            sys.exit(1)

        trace = response["trace"]

        h("3. RETRIEVAL — WHAT MATCHED, AND HOW WELL")
        print(f"  candidates after collapsing : {trace['candidates_before_threshold']}")
        print(f"  duplicates collapsed        : {trace['collapsed_duplicates']}"
              f"   (byte-identical chunks removed before ranking)")
        print(f"  cleared the {trace['min_score']} floor        : {len(trace['retrieved'])}")
        print(f"  retried with history        : {trace['retried_with_history']}")
        print(f"  embedding {trace['embed_ms']}ms + search {trace['search_ms']}ms")
        print()
        if not trace["retrieved"]:
            print("      nothing scored above the floor -> insufficient_context, "
                  "and the model was never called")
        for r in trace["retrieved"]:
            row = conn.execute(
                "select d.filename, c.page, c.ordinal, c.token_count, c.text "
                "from document_chunks c join documents d on d.id=c.document_id where c.id=%s",
                (r["chunk_id"],)).fetchone()
            if row is None:
                print(f"    rank {r['rank']}  score {r['score']:.4f}  (chunk no longer exists)")
                continue
            filename, page, ordinal, tokens, text = row
            label = "Close match" if r["score"] >= 0.68 else "Partial match"
            where = f"page {page}" if page else f"chunk {ordinal}"
            print(f"    rank {r['rank']}   score {r['score']:.4f}   {label}")
            print(f"           {filename}  ({where}, {tokens} tokens)")
            # --full-text prints the chunk in full. It matters for demonstrating that the
            # model was GIVEN the answer: a 240-character preview of a 267-token chunk cuts
            # off before the evidence does.
            shown_text = text if full_text else text[:240] + ("..." if len(text) > 240 else "")
            print(wrap(shown_text))
            print()

        if retrieve_only:
            return

        h("4. GENERATION")
        print(f"  prompt template      : {trace['prompt_template_version']}")
        print(f"  generation model     : {trace['generation_model']} @ {trace['generation_model_revision'][:12]}")
        print(f"  history turns sent   : {trace['history_turns_received']}")
        print(f"  prompt tokens        : {trace['prompt_tokens']}")
        print(f"  completion tokens    : {trace['completion_tokens']}"
              f"   (cap {settings.generation_max_new_tokens}"
              f"{' — HIT THE CAP, output was truncated' if trace['completion_tokens'] >= settings.generation_max_new_tokens else ''})")
        print(f"  generation time      : {trace['generate_ms'] / 1000:.1f}s")
        print(f"  TOTAL                : {trace['total_ms'] / 1000:.1f}s")

        h("5. WHAT THE MODEL SAID, VERBATIM")
        raw = trace.get("raw_model_reply")
        paths = {
            "json": "it returned a well-formed JSON object",
            "salvaged_json": "the object was CUT OFF by the token cap; the answer text was "
                             "recovered and the broken scaffolding discarded",
            "text_fallback": "it ignored the format instruction and wrote prose",
            "unparsed": "nothing usable came back",
        }
        print(f"  parse path           : {trace.get('parse_path') or '(none)'}"
              f"   — {paths.get(trace.get('parse_path'), 'unknown')}")
        print()
        if raw:
            for line in raw.splitlines()[:14]:
                print(f"      {line[:92]}")
            if len(raw.splitlines()) > 14:
                print(f"      ... ({len(raw)} characters total)")
        else:
            print("      (not captured — send include_raw)")

        h("6. IS THE ANSWER MADE OF THE DOCUMENTS?")
        overlap = trace.get("grounding_overlap", 0.0)
        print(f"  grounding overlap    : {overlap:.3f}   (floor {settings.min_grounding_overlap})")
        print("                         fraction of the answer's words found in the retrieved text")
        if trace.get("rejected_as_ungrounded"):
            print("  VERDICT              : WITHHELD — the answer was not made of the documents,")
            print("                         so it was suppressed rather than shown without a source")
        else:
            print("  VERDICT              : the answer is built from the retrieved text")

        h("7. CITATIONS — WHICH DOCUMENT, AND WHICH SENTENCE")
        print(f"  quotes the model gave that could NOT be matched back : {len(trace['dropped_quotes'])}")
        print("      (a quote matching nothing is DROPPED, never guessed at)\n")
        if not response["citations"]:
            print("      no citations resolved for this answer")
        for c in response["citations"]:
            row = conn.execute(
                "select d.filename, ch.page from document_chunks ch "
                "join documents d on d.id=ch.document_id where ch.id=%s", (c["chunk_id"],)).fetchone()
            filename, page = row if row else ("(chunk gone)", None)
            label = "Close match" if c["score"] >= 0.68 else "Partial match"
            print(f"      {filename}" + (f"   page {page}" if page else ""))
            print(f"      similarity {c['score']:.4f}  -> shown to the user as: {label}")
            print(wrap(f'"{c["quote"]}"'))
            print()

        h("8. WHAT THE USER SEES, AND WHETHER IT DIFFERS FROM THE MODEL")
        shown = response["answer"] or ""
        print(f"  outcome              : {response['outcome']}")
        print()
        print(wrap(shown or "(empty — nothing was shown)", indent="      "))
        print()

        # The point of this section: the model's words and the user's words are not the same
        # thing, and every step between them is a deliberate decision this service made.
        changes = []
        if raw is not None and raw.strip() != shown.strip():
            if trace.get("rejected_as_ungrounded"):
                changes.append("the answer was WITHHELD ENTIRELY — it was not made of the "
                               "retrieved documents, so the user was told the documents do "
                               "not cover the question rather than shown a sourceless answer")
            if trace.get("parse_path") == "salvaged_json":
                changes.append("the model ran into the token cap mid-sentence; the JSON "
                               "scaffolding was stripped so the user did not see ```json{...")
            elif trace.get("parse_path") == "json" and not trace.get("rejected_as_ungrounded"):
                changes.append("the answer text was lifted out of the JSON envelope; the "
                               "quotes the model supplied became citations rather than text")
            if trace["dropped_quotes"]:
                changes.append(f"{len(trace['dropped_quotes'])} quote(s) the model attributed "
                               "to the documents matched nothing and were dropped, so no "
                               "citation was shown for them")
        print(f"  model output == what the user saw ?   "
              f"{'YES — passed through unchanged' if not changes else 'NO'}")
        for change in changes:
            print(wrap(f"- {change}", indent="      "))
        print()


if __name__ == "__main__":
    main()
