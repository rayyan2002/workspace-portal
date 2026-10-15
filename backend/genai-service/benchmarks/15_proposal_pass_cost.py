"""Day 10: what does a second generation pass actually cost?

The architecture question is one pass or two. Folding the proposal into qa-v2 is free but
lengthens an instruction the Day 2 measurements showed the model already struggles to
follow. A second PROPOSE_V1 pass is clean but adds latency to a request that already takes
30-60s.

A third option falls out of reading the template: PROPOSE_V1 needs the CONTEXT only for
summarize-document, which quotes a sentence. create-task and lookup-knowledge need only the
user's message. Prefill runs at ~280 tok/s, so dropping ~2,600 tokens of context is worth
roughly 9 seconds — measured here rather than extrapolated.
"""
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from app.config import settings
from app.prompts import PROPOSE_V1, parse_proposal

tok = AutoTokenizer.from_pretrained(settings.generation_model, revision=settings.generation_model_revision)
model = AutoModelForCausalLM.from_pretrained(
    settings.generation_model, revision=settings.generation_model_revision, torch_dtype=torch.float32)
model.eval()

# A realistic retrieved set: five chunks at the real corpus median.
CHUNK = ("Rehearse this. A confident demo is worth more than an extra feature. "
         "The terminal shows each aircraft going through the maintenance pipeline. " * 12)
CHUNKS = [CHUNK] * settings.default_top_k

MESSAGES = [
    ("asks for an action", "create a task to review the runway inspection findings"),
    ("asks for an action", "remind me to follow up on the finance report"),
    ("just a question",    "what does the AeroTwin document say about the demo"),
]


def run(label: str, message: str, chunks: list[str]) -> tuple[float, int, int, str | None]:
    rendered = PROPOSE_V1.render(chunks, message)
    messages = [{"role": "system", "content": rendered.system}, {"role": "user", "content": rendered.user}]
    ids = tok([tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)],
              return_tensors="pt")
    n_prompt = int(ids.input_ids.shape[1])

    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=80, do_sample=settings.generation_do_sample,
                             pad_token_id=tok.eos_token_id)
    secs = time.perf_counter() - t0

    produced = int(out.shape[1]) - n_prompt
    reply = tok.decode(out[0][n_prompt:], skip_special_tokens=True)
    proposal = parse_proposal(reply, chunk_texts=chunks if chunks else None,
                              chunk_count=0 if not chunks else None)
    return secs, n_prompt, produced, proposal.tool


print(f"{'context':<12}{'message':<52}{'sec':>7}{'prompt':>8}{'out':>6}  proposed")
print("-" * 100)
totals = {}
for with_context in (True, False):
    label = "full (top_k=5)" if with_context else "none"
    chunks = CHUNKS if with_context else []
    times = []
    for kind, message in MESSAGES:
        secs, n_prompt, produced, tool = run(label, message, chunks)
        times.append(secs)
        print(f"{label:<12}{message[:50]:<52}{secs:>7.1f}{n_prompt:>8}{produced:>6}  {tool or 'none'}  ({kind})")
    totals[label] = sum(times) / len(times)
    print()

print("=" * 100)
for label, mean in totals.items():
    print(f"  mean second-pass cost, context={label:<16}: {mean:5.1f}s")
saved = totals["full (top_k=5)"] - totals["none"]
print(f"\n  dropping the context from the proposal pass saves {saved:.1f}s")
print(f"  for reference, a full /answer is 30-60s, and the timeout is {90}s")
