"""Is the batching penalty caused by MIXED chunk lengths (padding), not by length itself?

05 (real corpus, lengths 2-510) shows batch 1 is 2-3x faster, robustly.
06 (uniform lengths) shows no consistent penalty at 360-510 tokens.

Those disagree, so something about the real corpus is doing it. This compares the SAME
number of chunks, same total tokens, arranged two ways:

  HOMOGENEOUS  every chunk ~480 tokens
  MIXED        half near 510, half tiny — the shape of the real corpus

If batch 64 loses only in the MIXED case, padding is the mechanism and sentence-transformers'
length sorting does not fully save us.
"""
import time

import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

from app.config import settings

torch.set_num_threads(6)
tok = AutoTokenizer.from_pretrained(settings.embedding_model, revision=settings.embedding_model_revision)
model = SentenceTransformer(settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")

unit = "Final approval of any leave longer than four weeks rests with the line manager. "
long_text = tok.decode(tok.encode(unit * 40, add_special_tokens=False)[:480])
short_text = "Public holidays are not carried forward."

homogeneous = [long_text] * 64
mixed = [long_text if i % 2 == 0 else short_text for i in range(64)]

for name, texts in (("homogeneous (~480 each)", homogeneous), ("mixed (480 / ~10)", mixed)):
    total_tokens = sum(len(tok.encode(t, add_special_tokens=False)) for t in texts)
    model.encode(texts[:2], batch_size=1, normalize_embeddings=True, show_progress_bar=False)
    timings = {}
    for bs in (1, 64):
        t0 = time.perf_counter()
        model.encode(texts, batch_size=bs, normalize_embeddings=True, show_progress_bar=False)
        timings[bs] = time.perf_counter() - t0
    ratio = timings[64] / timings[1]
    print(f"{name:<26} {total_tokens:>6} real tokens   batch1 {timings[1]:5.1f}s   "
          f"batch64 {timings[64]:5.1f}s   ratio {ratio:.2f}  "
          f"{'batch 64 WINS' if ratio < 1 else 'batch 1 wins'}")

print("\nIf the mixed case has a much worse ratio, padding is the mechanism.")
