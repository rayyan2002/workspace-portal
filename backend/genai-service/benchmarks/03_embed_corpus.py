"""Day 4 verification: extract -> chunk -> embed, the full pipeline, on the real 21 documents."""
import subprocess
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

from app.config import settings
from app.ingestion import Embedder, UnsupportedDocument, chunk_document, extract

UP = Path(__file__).resolve().parents[2] / "uploads"
tok = AutoTokenizer.from_pretrained(settings.embedding_model, revision=settings.embedding_model_revision)
model = SentenceTransformer(settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")

embedder = Embedder(
    encode=lambda texts, bs: np.asarray(
        model.encode(list(texts), batch_size=bs, normalize_embeddings=True, show_progress_bar=False)
    ).tolist(),
    dim=settings.embedding_dim,
    model=settings.embedding_model,
    revision=settings.embedding_model_revision,
)
count = lambda t: len(tok.encode(t, add_special_tokens=False))

rows = subprocess.run(["psql", "-d", "knowledge_assistant", "-At", "-F|", "-c",
                       "SELECT id, filename FROM documents ORDER BY size_bytes DESC;"],
                      capture_output=True, text=True).stdout.strip().splitlines()

total, t_start = 0, time.perf_counter()
all_vecs, meta = [], []
print(f"{'document':<44}{'chunks':>7}{'embed s':>9}{'s/chunk':>9}")
print("-" * 70)
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
    chunks = chunk_document(doc, count, max_tokens=settings.max_chunk_tokens)
    t0 = time.perf_counter()
    embedded = embedder.embed_chunks(chunks)
    dt = time.perf_counter() - t0
    total += len(embedded)
    all_vecs += [e.embedding for e in embedded]
    meta += [(name, e.ordinal, e.section, e.page) for e in embedded]
    print(f"{name[:42]:<44}{len(embedded):>7}{dt:>9.1f}{dt/len(embedded):>9.2f}")

elapsed = time.perf_counter() - t_start
V = np.array(all_vecs, dtype=np.float32)
print("-" * 70)
print(f"  {total} vectors in {elapsed:.0f}s  ({elapsed/total:.2f}s per chunk)")
print(f"  shape {V.shape} | dtype {V.dtype} | bytes {V.nbytes/1024:.0f} KB")
print(f"  norms: min {np.linalg.norm(V,axis=1).min():.6f} max {np.linalg.norm(V,axis=1).max():.6f}")
print(f"  any NaN or inf: {bool(np.isnan(V).any() or np.isinf(V).any())}")

# NOTE: an earlier version of this script ended with a nearest-neighbour check that
# reported "129/177 (73%) have their nearest neighbour in the same document". THAT NUMBER
# WAS WRONG and has been removed rather than corrected here: it grouped by FILENAME, and two
# rows share the name AeroTwin_Defense_Prep.pdf while being different documents.
#
# Grouped by document id the real figure is 4/177 (2%) — because the corpus is ~4x
# duplicated, so nearly every chunk's nearest neighbour is its own byte-identical twin in a
# copy of the document. See 04_corpus_duplication.py, which does the analysis properly and
# separates "different document" from "identical text".
