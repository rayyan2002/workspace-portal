"""Why is DEFAULT_BATCH_SIZE = 1?  (~3 minutes)

Runs the sweep in BOTH directions. Batch size and time-into-the-run are otherwise perfectly
confounded: this CPU throttles under sustained all-core load, so "the biggest batch is
slowest" and "the last one measured is slowest" look identical from a single sweep.

Expected: batch 1 fastest in both directions -> the effect is real, not thermal.
"""
import subprocess
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

from app.config import settings
from app.ingestion import UnsupportedDocument, chunk_document, extract

UP = Path(__file__).resolve().parents[2] / "uploads"
tok = AutoTokenizer.from_pretrained(settings.embedding_model, revision=settings.embedding_model_revision)


def count(text: str) -> int:
    return len(tok.encode(text, add_special_tokens=False))


rows = subprocess.run(
    ["psql", "-d", "knowledge_assistant", "-At", "-F|", "-c",
     "SELECT id, filename FROM documents;"],
    capture_output=True, text=True).stdout.strip().splitlines()

texts: list[str] = []
for line in rows:
    doc_id, name = line.split("|", 1)
    path = UP / doc_id
    if not path.exists():
        continue
    try:
        doc = extract(path.read_bytes(), name)
    except UnsupportedDocument:
        continue
    if doc.is_empty:
        continue
    texts += [c.text for c in chunk_document(doc, count, max_tokens=settings.max_chunk_tokens)]

lengths = sorted(count(t) for t in texts)
print(f"{len(texts)} real chunks, median {lengths[len(lengths) // 2]} tokens\n")

model = SentenceTransformer(settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")
model.encode(texts[:4], batch_size=4, normalize_embeddings=True, show_progress_bar=False)  # warm

for direction in ("forward", "reverse"):
    sizes = (1, 4, 8, 16, 32, 64) if direction == "forward" else (64, 32, 16, 8, 4, 1)
    print(f"--- sweep {direction} ---")
    print(f"{'batch':>6}{'total s':>10}{'ms/chunk':>11}{'chunks/s':>10}")
    for bs in sizes:
        t0 = time.perf_counter()
        vecs = np.asarray(model.encode(texts, batch_size=bs, normalize_embeddings=True,
                                        show_progress_bar=False))
        dt = time.perf_counter() - t0
        print(f"{bs:>6}{dt:>10.1f}{dt / len(texts) * 1000:>11.0f}{len(texts) / dt:>10.1f}")
    print()

print(f"dim {vecs.shape[1]} | norm of row 0: {np.linalg.norm(vecs[0]):.6f}")
a = np.asarray(model.encode([texts[0]], normalize_embeddings=True))
b = np.asarray(model.encode([texts[0]], normalize_embeddings=True))
print(f"determinism: same text twice -> max abs diff {float(np.abs(a - b).max()):.2e}")
