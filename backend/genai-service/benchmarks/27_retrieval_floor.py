"""Day 19: the floor itself, measured against every question that has ever failed here.

WHY THIS EXISTS. Three separate complaints this week resolved to one number:

    admission chunk      0.588   floor 0.60   missed by 0.012
    university policy    0.593   floor 0.60   missed by 0.007
    ai safety (typo)     0.535   floor 0.60

Each was answered with a fix in FRONT of the floor — anchored expansion, a better failure
message, spelling correction — while `default_min_score` was twice left alone with
"deliberately NOT changed" in the commit. This measures the thing itself.

THE CONSTRAINT THAT DECIDES IT is not recall. It is the unanswerable questions: the floor is
what produces `insufficient_context`, and a floor under their top score means the service
starts answering questions the corpus cannot answer. That is the worse failure, because it
is invisible — nothing in the output says the passages were irrelevant.

    ./.venv/bin/python benchmarks/27_retrieval_floor.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from app.config import settings  # noqa: E402

GOLDEN = ROOT / "evaluation" / "golden_questions.json"

# Questions a real user typed that failed. Not hypotheticals — each appears in a complaint.
REPORTED = [
    ("what is university policy", "University_Admission_Prospectus_2027.pdf"),
    ("WHAT IS THE ADMISSION POLICY", "University_Admission_Prospectus_2027.pdf"),
    ("what is the admission process?", "University_Admission_Prospectus_2027.pdf"),
    ("tell me about ai safety", "AI_safety.pdf"),
    ("summarise abstract of ai-safety research paper", "AI_safety.pdf"),
]

SQL = """
SELECT d.filename, c.text, -(c.embedding <#> %(q)s::vector) AS s
FROM document_chunks c JOIN documents d ON d.id = c.document_id
ORDER BY c.embedding <#> %(q)s::vector LIMIT 40
"""


def _gate(rows, floor, top_k, max_documents):
    """The production gate, in miniature: floor, then the document cap, then top_k."""
    kept = [r for r in rows if r[2] >= floor]
    if max_documents:
        allowed = []
        for fn, _b, _s in kept:
            if fn not in allowed and len(allowed) < max_documents:
                allowed.append(fn)
        kept = [r for r in kept if r[0] in allowed]
    return kept[:top_k]


def main() -> None:
    golden = json.loads(GOLDEN.read_text())["questions"]
    answerable = [(q["question"], q.get("expect_document")) for q in golden if q["answerable"]]
    unanswerable = [q["question"] for q in golden if not q["answerable"]]

    model = SentenceTransformer(
        settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")

    def rank(conn, text):
        v = model.encode([settings.query_prefix + text], normalize_embeddings=True)[0]
        literal = "[" + ",".join(repr(float(x)) for x in v) + "]"
        rows = conn.execute(SQL, {"q": literal}).fetchall()
        seen, out = set(), []
        for fn, body, score in rows:          # collapse byte-identical text, as rank_rows does
            if body in seen:
                continue
            seen.add(body)
            out.append((fn, body, float(score)))
        return out

    with psycopg.connect(settings.dsn) as conn:
        ranked = {q: rank(conn, q) for q, _ in answerable + REPORTED}
        ranked.update({q: rank(conn, q) for q in unanswerable})

    print(f"  {len(answerable)} golden answerable, {len(REPORTED)} reported failures, "
          f"{len(unanswerable)} unanswerable\n")
    print(f"  {'floor':>6} {'golden':>8} {'reported':>9} {'LEAKED':>8} {'noise':>7} {'tok/q':>7}")
    print("  " + "-" * 52)

    top_k = settings.default_top_k
    for floor in [round(0.50 + i * 0.01, 2) for i in range(16)]:
        g = sum(any(fn == want for fn, _b, s in ranked[q][:top_k] if s >= floor)
                for q, want in answerable)
        r = sum(any(fn == want for fn, _b, s in ranked[q][:top_k] if s >= floor)
                for q, want in REPORTED)
        leaked = sum(len([1 for _f, _b, s in ranked[q][:top_k] if s >= floor])
                     for q in unanswerable)
        noise = sum(len([1 for fn, _b, s in ranked[q][:top_k] if s >= floor and fn != want])
                    for q, want in answerable + REPORTED)
        chars = sum(len(b) for q, _w in answerable + REPORTED
                    for _f, b, s in ranked[q][:top_k] if s >= floor)
        tok = chars // 4 // (len(answerable) + len(REPORTED))
        flag = "  <-- answers what the corpus cannot" if leaked else ""
        print(f"  {floor:>6.2f} {f'{g}/{len(answerable)}':>8} {f'{r}/{len(REPORTED)}':>9} "
              f"{leaked:>8} {noise:>7} {tok:>7}{flag}")

    # The second half of the decision. A lower floor doubles off-document noise; capping
    # how many DOCUMENTS may contribute removes it, because the noise was never the
    # threshold — it was other documents, and document selection is what this embedder does
    # reliably (9/9 on the golden set).
    print(f"\n  {'policy':34} {'hits':>7} {'off-doc':>8} {'leaked':>7} {'tok/q':>7}")
    print("  " + "-" * 66)
    everything = answerable + REPORTED
    for label, floor, max_docs in (("0.60, any document", 0.60, 0),
                                   ("0.55, any document", 0.55, 0),
                                   ("0.55, top 1 document", 0.55, 1),
                                   ("0.55, top 2 documents", 0.55, 2)):
        hits = noise = chars = 0
        for q, want in everything:
            kept = _gate(ranked[q], floor, top_k, max_docs)
            hits += any(fn == want for fn, _b, _s in kept)
            noise += sum(1 for fn, _b, _s in kept if fn != want)
            chars += sum(len(b) for _f, b, _s in kept)
        leaked = sum(len(_gate(ranked[q], floor, top_k, max_docs)) for q in unanswerable)
        print(f"  {label:34} {f'{hits}/{len(everything)}':>7} {noise:>8} {leaked:>7} "
              f"{chars // 4 // len(everything):>7}")

    # THE THIRD PART, and the one the golden set could not have found. The unanswerable
    # golden questions score 0.44-0.52, so a 0.55 floor looks safe against them. REAL
    # off-topic questions score far higher because they share vocabulary with the corpus:
    # "Follow up on finance" reaches 0.5925 on an aviation deck, one ten-thousandth below
    # "what is university policy" at 0.5926. No floor separates those. The DOCUMENT margin
    # does, and only in the band where it is needed.
    print("\n  the marginal band, on REAL questions from the chat history:")
    print(f"    {'question':44} {'top':>7} {'margin':>8}  kept?")
    with psycopg.connect(settings.dsn) as conn:
        real = [r[0] for r in conn.execute(
            "SELECT DISTINCT content FROM messages WHERE sender='user' "
            "AND length(content) > 8").fetchall()]
        for q in real:
            rows = rank(conn, q)
            best: dict[str, float] = {}
            for fn, _b, s in rows:
                best.setdefault(fn, s)
            order = sorted(best.values(), reverse=True)
            top = order[0]
            if not settings.default_min_score <= top < settings.confident_score:
                continue
            margin = top - (order[1] if len(order) > 1 else 0.0)
            kept = "keep" if margin >= settings.min_document_margin else "refuse"
            print(f"    {q[:44]:44} {top:7.4f} {margin:8.4f}  {kept}")

    print("\n  the unanswerable ceiling — the floor must stay above this:")
    for q in unanswerable:
        print(f"    {ranked[q][0][2]:.4f}  {q[:52]}")


if __name__ == "__main__":
    main()
