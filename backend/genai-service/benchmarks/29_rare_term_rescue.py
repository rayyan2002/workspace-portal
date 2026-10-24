"""Day 20: the proposal pointed at the wrong document, and the floor was not the reason.

REPORTED. "summarize features of swift" proposed summarising
`AI_Assessment_Nisum_Alpha_A_Zohaib_Ali_graded (1).csv`, while
`Suzuki_Swift_2026_Pakistan_Guide.pdf` — which contains "swift" seven times and is the only
document in the corpus that contains it at all — was not retrieved. The service's own trace
said so: verdict `weak_evidence`, suspect `retrieval`, best chunk 0.544 under a 0.55 floor,
six of seven chunks admitted only by anchored expansion AFTER the wrong document anchored.

WHAT IT IS NOT. Not the floor, and not the word "summarize". Measured:

    swift                                    Suzuki  0.6123  rank 1
    Suzuki Swift features                    Suzuki  0.7659  rank 1
    summarize features of swift              CSV     0.6179  Suzuki rank 10 (0.5146)
    features of swift        (no "summarize")AI_safety       Suzuki rank  8 (0.5519)
    summarize features of the training tracker       AI_safety 0.7139  tracker not even top

Dropping "summarize" does not fix it, and asking for the training tracker BY NAME loses to
AI_safety.pdf. The pattern is that generic scaffolding words ("features of ...") dominate a
short query's embedding and the one rare token that identifies the document is outvoted.

THE IDEA UNDER TEST: a term's DOCUMENT FREQUENCY already says how much it identifies a
document. "swift" appears in 1 document of 20; "features" appears in many. So rank candidate
documents by how many SELECTIVE query terms they contain, breaking ties by the dense score.

    selective(term)  ==  1 <= documents containing it <= MAX_DF

This needs no stopword list, which is the point — df calibrates itself against this corpus,
where a hand-written list would be my guess about which words matter. And it is a NO-OP when
the query holds no selective term: every candidate scores 0 and the dense order is returned
untouched. That is the property that decides whether it is safe, so it is measured, not
asserted: the golden set and every previously reported failure are re-run through it.

    ./.venv/bin/python benchmarks/29_rare_term_rescue.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from app.config import settings  # noqa: E402

GOLDEN = ROOT / "evaluation" / "golden_questions.json"

#: A term that identifies a document appears in exactly ONE, and appears there REPEATEDLY.
#: df alone was measured and is not enough: on a 15-document corpus ordinary English words
#: land at df 1 by accident — `contain` (2 occurrences), `world`, `home` — and promoting on
#: them broke the project-setup question. Occurrence count separates the accident from the
#: signal: `swift` 26, `suzuki` 21, `aerotwin` 42 against `contain` 2.
MAX_DF = 1
MIN_OCCURRENCES = 5
#: Shorter tokens are noise ("the", "ai", "of"), and "ai" would match half the corpus.
MIN_TERM = 4

REPORTED = [
    ("what is university policy", "University_Admission_Prospectus_2027.pdf"),
    ("WHAT IS THE ADMISSION POLICY", "University_Admission_Prospectus_2027.pdf"),
    ("what is the admission process?", "University_Admission_Prospectus_2027.pdf"),
    ("tell me about ai safety", "AI_safety.pdf"),
    ("summarise abstract of ai-safety research paper", "AI_safety.pdf"),
    # Today's report, and the phrasings that bracket it.
    ("summarize features of swift", "Suzuki_Swift_2026_Pakistan_Guide.pdf"),
    ("features of swift", "Suzuki_Swift_2026_Pakistan_Guide.pdf"),
    ("summarize swift", "Suzuki_Swift_2026_Pakistan_Guide.pdf"),
    ("swift", "Suzuki_Swift_2026_Pakistan_Guide.pdf"),
]

SQL = """
SELECT d.filename, c.text, -(c.embedding <#> %(q)s::vector) AS s
FROM document_chunks c JOIN documents d ON d.id = c.document_id
ORDER BY c.embedding <#> %(q)s::vector LIMIT 60
"""


def corpus_index(conn):
    """(term -> filenames containing it, term -> total occurrences). Built once."""
    rows = conn.execute(
        "SELECT d.filename, c.text FROM document_chunks c "
        "JOIN documents d ON d.id = c.document_id").fetchall()
    df: dict[str, set[str]] = {}
    occ: dict[str, int] = {}
    for filename, text in rows:
        tokens = re.findall(rf"[a-z]{{{MIN_TERM},}}", text.lower())
        for term in set(tokens):
            df.setdefault(term, set()).add(filename)
        for term in tokens:
            occ[term] = occ.get(term, 0) + 1
    return df, occ


def selective_terms(question, df, occ) -> dict[str, set[str]]:
    """Query terms that identify ONE document and recur inside it."""
    out = {}
    for term in set(re.findall(rf"[a-z]{{{MIN_TERM},}}", question.lower())):
        docs = df.get(term)
        if docs and len(docs) <= MAX_DF and occ.get(term, 0) >= MIN_OCCURRENCES:
            out[term] = docs
    return out


def rescue(ranked, question, df, occ, floor, doc_best):
    """Promote the document a selective term names, if it clears `floor`.

    RE-RANKING ALONE WAS NOT ENOUGH and that was measured: for "summarize features of
    swift" the Suzuki guide is not in the dense top 60 at all, so there was nothing to
    reorder. The document has to be ADMITTED, which means reaching past what dense
    retrieval surfaced — and that is exactly where a rescue could start answering
    questions the corpus cannot, so admission is gated on its own floor.

    Returns (ordered filenames, selective terms). No selective term == identity.
    """
    terms = selective_terms(question, df, occ)
    best: dict[str, float] = {}
    for filename, _body, score in ranked:
        best.setdefault(filename, score)

    # Reach past the dense candidates for documents a selective term names.
    for docs in terms.values():
        for fn in docs:
            if fn not in best and doc_best.get(fn, -1.0) >= floor:
                best[fn] = doc_best[fn]

    covered = {fn: sum(1 for docs in terms.values() if fn in docs) for fn in best}
    # A promoted document must still clear the floor; coverage never beats the floor.
    order = sorted(best, key=lambda fn: (-(covered[fn] if best[fn] >= floor else 0), -best[fn]))
    return order, terms


def main() -> None:
    golden = json.loads(GOLDEN.read_text())["questions"]
    answerable = [(q["question"], q["expect_document"]) for q in golden if q["answerable"]]
    unanswerable = [q["question"] for q in golden if not q["answerable"]]
    cases = answerable + REPORTED

    model = SentenceTransformer(
        settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")

    BEST_PER_DOC = """
    SELECT d.filename, max(-(c.embedding <#> %(q)s::vector)) AS s
    FROM document_chunks c JOIN documents d ON d.id = c.document_id GROUP BY d.filename
    """

    with psycopg.connect(settings.dsn) as conn:
        df, occ = corpus_index(conn)
        total_docs = len({fn for docs in df.values() for fn in docs})
        sel = {t for t in df if len(df[t]) <= MAX_DF and occ.get(t, 0) >= MIN_OCCURRENCES}
        print(f"\n  {len(df)} distinct terms over {total_docs} documents")
        print(f"  selective = df <= {MAX_DF} and occurrences >= {MIN_OCCURRENCES}"
              f"  ->  {len(sel)} terms qualify\n")

        def embed(text):
            v = model.encode([settings.query_prefix + text], normalize_embeddings=True)[0]
            return "[" + ",".join(repr(float(x)) for x in v) + "]"

        cache = {}
        for q, _w in cases + [(u, None) for u in unanswerable]:
            lit = embed(q)
            rows = conn.execute(SQL, {"q": lit}).fetchall()
            seen, ranked = set(), []
            for fn, body, score in rows:
                if body in seen:
                    continue
                seen.add(body)
                ranked.append((fn, body, float(score)))
            doc_best = {fn: float(s) for fn, s in
                        conn.execute(BEST_PER_DOC, {"q": lit}).fetchall()}
            cache[q] = (ranked, doc_best)

        print(f"    {'rescue floor':>12} {'fixed':>6} {'broke':>6} {'already ok':>11} "
              f"{'still wrong':>12} {'LEAKED':>7}")
        print("    " + "-" * 62)
        for floor in (0.40, 0.45, 0.50, 0.52, 0.55):
            fixed = broke = same_ok = same_bad = 0
            for q, want in cases:
                ranked, doc_best = cache[q]
                d_order, _ = rescue(ranked, q, {}, {}, floor, {})
                n_order, _ = rescue(ranked, q, df, occ, floor, doc_best)
                d_ok, n_ok = d_order[0] == want, n_order[0] == want
                if d_ok and n_ok:
                    same_ok += 1
                elif n_ok:
                    fixed += 1
                elif d_ok:
                    broke += 1
                else:
                    same_bad += 1
            # A rescue must never give an unanswerable question a document above the
            # PRODUCTION floor — that is the failure nothing in the output would show.
            leaked = 0
            for u in unanswerable:
                ranked, doc_best = cache[u]
                order, terms = rescue(ranked, u, df, occ, floor, doc_best)
                if terms and doc_best.get(order[0], 0.0) >= settings.default_min_score:
                    leaked += 1
            print(f"    {floor:>12.2f} {fixed:>6} {broke:>6} {same_ok:>11} "
                  f"{same_bad:>12} {leaked:>7}")

        FLOOR = 0.50
        print(f"\n    case by case at rescue floor {FLOOR}:")
        print(f"      {'question':44} {'dense':28} {'rescued':28} verdict")
        print("      " + "-" * 112)
        for q, want in cases:
            ranked, doc_best = cache[q]
            d_order, _ = rescue(ranked, q, {}, {}, FLOOR, {})
            n_order, terms = rescue(ranked, q, df, occ, FLOOR, doc_best)
            d_ok, n_ok = d_order[0] == want, n_order[0] == want
            v = "ok" if (d_ok and n_ok) else ("FIXED" if n_ok else
                                              ("BROKE" if d_ok else "still wrong"))
            print(f"      {q[:44]:44} {d_order[0][:28]:28} {n_order[0][:28]:28} {v}")
            if terms:
                print(f"        {'':44} terms: {sorted(terms)}")

        print("\n    unanswerable questions — selective terms found, and the best score:")
        for u in unanswerable:
            ranked, doc_best = cache[u]
            terms = selective_terms(u, df, occ)
            top = max(doc_best.values()) if doc_best else 0.0
            shown = ", ".join(sorted(terms)) or "none"
            print(f"      {u[:48]:48} terms={shown:28} best any doc {top:.4f}")


if __name__ == "__main__":
    main()
