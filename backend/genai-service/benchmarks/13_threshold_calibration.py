"""Day 6: where does min_score actually belong?

`min_score` decides `insufficient_context` in CODE, before the generation model is ever
called, so a threshold in the wrong place is not a tuning detail — it decides whether the
service can ever say "I don't know".

This prints three things:
  1. the score real questions get,
  2. the score questions the corpus PROVABLY cannot answer get (the noise floor),
  3. which of the "answerable" anchors are seeded stubs and therefore lying to us.

(3) exists because the first run of this benchmark flattered itself: two of the four
answerable anchors were placeholder files whose entire body is their own filename, so
they scored high on echo rather than on retrieval. A calibration contaminated by the
corpus defect it is meant to survive is the same failure as a benchmark measuring its
own test data.
"""
import numpy as np
import psycopg
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.retrieval import _vector_literal

model = SentenceTransformer(
    settings.embedding_model, revision=settings.embedding_model_revision, device="cpu"
)

ANSWERABLE = [
    "What does the AeroTwin defense preparation document cover?",
    "What is covered in the GenAI training tracker?",
    "What were the quarterly financial results?",
    "How is the FastAPI proxy architecture structured?",
]
UNANSWERABLE = [
    "What is the capital of France?",
    "How do I bake sourdough bread at home?",
    "What is the airspeed velocity of an unladen swallow?",
    "Who won the 1998 FIFA World Cup final?",
]

# A chunk whose body is "Placeholder content for a <filename>" scores on filename echo.
STUB = "Placeholder content"

SQL = """
SELECT -(c.embedding <#> %(q)s::vector) AS score, c.text, d.filename
FROM document_chunks c JOIN documents d ON d.id = c.document_id
ORDER BY c.embedding <#> %(q)s::vector
LIMIT 1
"""


def top1(conn, question: str) -> tuple[float, str, str]:
    vector = np.asarray(
        model.encode([settings.query_prefix + question], normalize_embeddings=True)
    )[0].tolist()
    score, text, filename = conn.execute(SQL, {"q": _vector_literal(vector)}).fetchone()
    return float(score), text, filename


with psycopg.connect(settings.dsn) as conn:
    print(f"{'question':<52}{'top1':>7}  source")
    print("-" * 96)
    genuine, contaminated = [], []
    for q in ANSWERABLE:
        score, text, filename = top1(conn, q)
        is_stub = STUB in text
        (contaminated if is_stub else genuine).append(score)
        flag = "  <- SEEDED STUB: filename echo, not retrieval" if is_stub else ""
        print(f"{q:<52}{score:>7.3f}  {filename[:28]}{flag}")

    print()
    noise = []
    for q in UNANSWERABLE:
        score, _text, filename = top1(conn, q)
        noise.append(score)
        print(f"{q:<52}{score:>7.3f}  {filename[:28]}")

    floor = max(noise)
    print("\n" + "=" * 96)
    print(f"  noise floor (best UNANSWERABLE score)   : {floor:.3f}")
    print(f"  genuine anchors                         : {[f'{s:.3f}' for s in genuine]}")
    print(f"  stub-contaminated anchors (DISCARD)     : {[f'{s:.3f}' for s in contaminated]}")
    if genuine:
        print(f"  usable separation gap                   : {min(genuine) - floor:+.3f}"
              f"  (n={len(genuine)}, not {len(ANSWERABLE)})")
        print(f"  midpoint                                : {(min(genuine) + floor) / 2:.3f}")
    print(f"  configured default_min_score            : {settings.default_min_score}")
    print(f"  0.35 would have rejected                 : "
          f"{sum(1 for s in noise if s < 0.35)}/{len(noise)} unanswerable questions")
    print(f"  {settings.default_min_score} rejects                            : "
          f"{sum(1 for s in noise if s < settings.default_min_score)}/{len(noise)}")
