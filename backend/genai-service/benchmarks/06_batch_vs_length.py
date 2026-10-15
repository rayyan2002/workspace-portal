"""Is SEQUENCE LENGTH the variable that decides whether batching helps?

The 220-token test said batch 16 wins at 6 threads. The real corpus (median 478) said
batch 1 wins. Same machine, same thread count. Length is the obvious difference — attention
and activations grow with it, so a batch of 16 long sequences holds far more live memory.

Uniform lengths throughout, so padding is never a factor.
"""
import time

import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

from app.config import settings

torch.set_num_threads(6)
tok = AutoTokenizer.from_pretrained(settings.embedding_model, revision=settings.embedding_model_revision)
m = SentenceTransformer(settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")
unit = "Final approval of any leave longer than four weeks rests with the line manager. "

print(f"{'tokens/chunk':>13}{'batch=1':>10}{'batch=16':>10}{'ratio':>8}   verdict")
print("-" * 60)
for reps in (8, 24, 48, 72):
    text = unit * reps
    n = len(tok.encode(text, add_special_tokens=False))
    if n > settings.max_chunk_tokens:
        text = tok.decode(tok.encode(text, add_special_tokens=False)[:settings.max_chunk_tokens])
        n = settings.max_chunk_tokens
    texts = [text] * 24
    m.encode(texts[:2], batch_size=1, normalize_embeddings=True, show_progress_bar=False)

    t = {}
    for bs in (1, 16):
        t0 = time.perf_counter()
        m.encode(texts, batch_size=bs, normalize_embeddings=True, show_progress_bar=False)
        t[bs] = time.perf_counter() - t0
    ratio = t[16] / t[1]
    print(f"{n:>13}{t[1]:>9.1f}s{t[16]:>9.1f}s{ratio:>8.2f}   "
          f"{'batch 16 wins' if ratio < 1 else 'batch 1 wins'}")

print("\nratio < 1 means batching helps; > 1 means it hurts.")
print("If the ratio climbs with length, sequence length is the deciding variable.")
