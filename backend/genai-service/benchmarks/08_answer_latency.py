"""What does an answer ACTUALLY cost with real chunks from a real document?

Every timing so far used hand-written chunks of ~50 tokens. Real chunks have a median of
478. That is a ~10x difference in prefill, so the earlier 7.3s mean is not the number a
user would experience.
"""
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from app.config import settings
from app.ingestion import chunk_document, extract
from app.prompts import QA_V2, parse_quoted_answer

emb_tok = AutoTokenizer.from_pretrained(settings.embedding_model, revision=settings.embedding_model_revision)
gen_tok = AutoTokenizer.from_pretrained(settings.generation_model, revision=settings.generation_model_revision)
model = AutoModelForCausalLM.from_pretrained(
    settings.generation_model, revision=settings.generation_model_revision, torch_dtype=torch.float32)
model.eval()

UP = Path(__file__).resolve().parents[2] / "uploads"
data = (UP / "6a50fc1e-c43f-4c14-b61c-5188bec94633").read_bytes()
doc = extract(data, "AeroTwin_Defense_Prep.pdf")
chunks = chunk_document(doc, lambda t: len(emb_tok.encode(t, add_special_tokens=False)),
                        max_tokens=settings.max_chunk_tokens)
print(f"document: {len(chunks)} chunks, median {sorted(c.token_count for c in chunks)[len(chunks)//2]} tokens\n")

QUESTION = "What are the main defense preparation requirements described in this document?"

for top_k in (3, 5):
    selected = chunks[:top_k]
    rendered = QA_V2.render([c.text for c in selected], QUESTION)
    msgs = [{"role": "system", "content": rendered.system}, {"role": "user", "content": rendered.user}]
    ids = gen_tok([gen_tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)],
                  return_tensors="pt")
    n_prompt = ids.input_ids.shape[1]

    with torch.no_grad():
        t0 = time.perf_counter(); model(**ids); prefill = time.perf_counter() - t0

    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=200, do_sample=True, temperature=0.7,
                             top_p=0.8, top_k=20, pad_token_id=gen_tok.eos_token_id)
    total = time.perf_counter() - t0
    produced = out.shape[1] - n_prompt
    reply = gen_tok.decode(out[0][n_prompt:], skip_special_tokens=True)
    p = parse_quoted_answer(reply, [c.text for c in selected])

    print(f"top_k={top_k}")
    print(f"  prompt        : {n_prompt} tokens  ({sum(c.token_count for c in selected)} of them context)")
    print(f"  prefill       : {prefill:.1f}s")
    print(f"  generation    : {total:.1f}s for {produced} tokens")
    print(f"  TOTAL         : {prefill + total:.1f}s   <- what the user waits, plus ~0.1s retrieval")
    print(f"  worst case    : {prefill + (200/ (produced/max(total-0,1e-9)) if produced else 0):.1f}s if it runs to the 200-token cap")
    print(f"  cited         : {p.cited}  answer: {p.answer[:70]!r}\n")
