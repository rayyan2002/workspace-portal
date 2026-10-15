"""Does batching hurt because ONE sequence already saturates the cores?

Direct test. If that is the mechanism, then starving the process of cores should REVERSE
the result: with 1 thread a single sequence cannot saturate anything, so batching should
help. With 6 threads it already does, so batching should hurt.

If batch 1 still wins at 1 thread, the explanation is wrong and it is something else
(cache pressure, padding, allocator overhead).
"""
import time

import torch
from sentence_transformers import SentenceTransformer

from app.config import settings

texts = [("Final approval of any leave longer than four weeks rests with the line manager. " * 12)] * 24
print(f"{len(texts)} chunks of ~{len(texts[0].split())} words each (uniform length: padding is NOT a factor)\n")
print(f"{'threads':>8}{'batch=1':>10}{'batch=16':>10}   verdict")
print("-" * 52)

for threads in (1, 2, 6):
    torch.set_num_threads(threads)
    m = SentenceTransformer(settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")
    m.encode(texts[:2], batch_size=1, normalize_embeddings=True, show_progress_bar=False)  # warm

    timings = {}
    for bs in (1, 16):
        t0 = time.perf_counter()
        m.encode(texts, batch_size=bs, normalize_embeddings=True, show_progress_bar=False)
        timings[bs] = time.perf_counter() - t0

    faster = "batch 16 WINS" if timings[16] < timings[1] else "batch 1 wins"
    ratio = timings[16] / timings[1]
    print(f"{threads:>8}{timings[1]:>9.1f}s{timings[16]:>9.1f}s   {faster}  (16/1 = {ratio:.2f}x)")

print("\nIf the ratio falls as threads rise, batching is competing with thread parallelism")
print("for the same cores — which is the stated hypothesis.")
