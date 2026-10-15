"""Day 7: does the answer parse, and does it cite? Greedy vs sampled, same questions.

qa-v2 resolves a citation by matching the model's QUOTE back to chunk text, so decoding
is not a style setting — it decides whether a citation exists at all. The first live
/answer call returned markdown prose, ran to the 200-token cap, and cited nothing. This
measures whether that is greedy decoding or the prompt.
"""
import json
import time

import psycopg
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer

from app.answering import answer_question
from app.config import settings
from app.prompts import template_for
from app.retrieval import retrieve

emb = SentenceTransformer(settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")
tok = AutoTokenizer.from_pretrained(settings.generation_model, revision=settings.generation_model_revision)
gen = AutoModelForCausalLM.from_pretrained(
    settings.generation_model, revision=settings.generation_model_revision, torch_dtype=torch.float32)
gen.eval()

OWNER = "83814a60-6bd4-427a-8382-8972debaa6ca"
with psycopg.connect(settings.dsn) as c:
    ALLOWED = [r[0] for r in c.execute("select id from documents where owner_id=%s", (OWNER,)).fetchall()]

QUESTIONS = [
    "What is covered in the GenAI training tracker?",
    "What does the AeroTwin document say about the demo?",
    "What is in the review rubric?",
]

RAW = {}


def make_generate(do_sample: bool):
    def generate(system: str, user: str):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tok([prompt], return_tensors="pt")
        n = int(inputs.input_ids.shape[1])
        kwargs = {"max_new_tokens": settings.generation_max_new_tokens,
                  "do_sample": do_sample, "pad_token_id": tok.eos_token_id}
        if do_sample:
            kwargs |= {"temperature": settings.generation_temperature,
                       "top_p": settings.generation_top_p, "top_k": settings.generation_top_k}
        with torch.no_grad():
            out = gen.generate(**inputs, **kwargs)
        reply = tok.decode(out[0][n:], skip_special_tokens=True)
        RAW["last"] = reply
        return reply, n, int(out.shape[1]) - n
    return generate


def looks_like_json(raw: str) -> bool:
    try:
        json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        return True
    except (ValueError, IndexError):
        return False


print(f"{'mode':<9}{'question':<46}{'sec':>6}{'out_tok':>8}{'json':>6}{'cites':>7}{'drop':>6}")
print("-" * 92)
summary = {}
for do_sample in (False, True):
    mode = "sampled" if do_sample else "greedy"
    rows = []
    for q in QUESTIONS:
        r = retrieve(lambda t: emb.encode([settings.query_prefix + t], normalize_embeddings=True)[0].tolist(),
                     q, ALLOWED, settings.default_top_k, settings.default_min_score)
        t0 = time.perf_counter()
        a = answer_question(r, q, template_for(settings.prompt_template_version), make_generate(do_sample))
        secs = time.perf_counter() - t0
        ok = looks_like_json(RAW.get("last", ""))
        rows.append((secs, a.completion_tokens, ok, len(a.citations), len(a.dropped_quotes)))
        print(f"{mode:<9}{q[:44]:<46}{secs:>6.1f}{a.completion_tokens:>8}{str(ok):>6}"
              f"{len(a.citations):>7}{len(a.dropped_quotes):>6}")
    summary[mode] = rows

print("\n" + "=" * 92)
for mode, rows in summary.items():
    n = len(rows)
    print(f"  {mode:<8} mean {sum(r[0] for r in rows)/n:>5.1f}s | "
          f"hit 200-tok cap {sum(r[1] >= settings.generation_max_new_tokens for r in rows)}/{n} | "
          f"parsed as JSON {sum(r[2] for r in rows)}/{n} | "
          f"answers with >=1 citation {sum(r[3] > 0 for r in rows)}/{n}")
print(f"\n  config default is do_sample={settings.generation_do_sample}")
print(f"\n  last raw reply (first 200 chars):\n    {RAW.get('last','')[:200]!r}")
