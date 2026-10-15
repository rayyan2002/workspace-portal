"""Day 10: the routing decision — model, or Spring's keyword triggers?

Not a rhetorical comparison. Spring already ships a keyword proposer, so the model has to
BEAT it to be worth a second generation pass. The set below deliberately includes cases
built to trip each approach: phrases containing a trigger word inside an ordinary question
(where keywords should false-positive) and action requests phrased without any trigger word
(where keywords should miss).

A false positive is the expensive error. parse_proposal says why: a wrongly-proposed action
puts a decision in front of a human that should never have been raised.
"""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from app.config import settings
from app.prompts import PROPOSE_V1, parse_proposal

# Copied verbatim from ChatSessionService.TASK_TRIGGERS.
TASK_TRIGGERS = [
    "create a task", "create task", "add a task", "make a task",
    "remind me", "reminder", "todo", "to-do", "to do",
    "follow up", "follow-up", "action item", "track this", "assign",
]

# (message, should_propose)
CASES = [
    ("create a task to review the runway inspection findings", True),
    ("remind me to follow up on the finance report", True),
    ("add a task for the demo rehearsal", True),
    # An action request with NO trigger phrase — keywords should miss this.
    ("can you note down that the ADBMS sheet needs updating", True),
    ("what are the formulas of adbms", False),
    ("what is the fleet size", False),
    ("tell me in detail", False),
    # Trigger words inside an ordinary QUESTION — keywords should false-positive here.
    ("what does the document say about follow up procedures", False),
    ("is there a todo list in the quarterly report", False),
]

tok = AutoTokenizer.from_pretrained(settings.generation_model, revision=settings.generation_model_revision)
model = AutoModelForCausalLM.from_pretrained(
    settings.generation_model, revision=settings.generation_model_revision, torch_dtype=torch.float32)
model.eval()


def keywords_propose(message: str) -> bool:
    return any(t in message.lower() for t in TASK_TRIGGERS)


def model_proposes(message: str) -> bool:
    rendered = PROPOSE_V1.render([], message)
    chat = [{"role": "system", "content": rendered.system}, {"role": "user", "content": rendered.user}]
    ids = tok([tok.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)], return_tensors="pt")
    n = int(ids.input_ids.shape[1])
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=80, do_sample=False, pad_token_id=tok.eos_token_id)
    reply = tok.decode(out[0][n:], skip_special_tokens=True)
    return parse_proposal(reply, chunk_count=0).tool is not None


def score(name, predictions):
    tp = sum(1 for (_, want), got in zip(CASES, predictions, strict=False) if want and got)
    fp = sum(1 for (_, want), got in zip(CASES, predictions, strict=False) if not want and got)
    fn = sum(1 for (_, want), got in zip(CASES, predictions, strict=False) if want and not got)
    tn = sum(1 for (_, want), got in zip(CASES, predictions, strict=False) if not want and not got)
    print(f"  {name:<10} correct {tp + tn}/{len(CASES)}   "
          f"missed {fn}   FALSE POSITIVES {fp}  <- the expensive error")
    return tp, fp, fn, tn


kw = [keywords_propose(m) for m, _ in CASES]
md = [model_proposes(m) for m, _ in CASES]

print(f"{'message':<56}{'want':>6}{'keywords':>10}{'model':>8}")
print("-" * 82)
for (message, want), k, m in zip(CASES, kw, md, strict=False):
    flag = "" if (k == want and m == want) else "   <-"
    print(f"{message[:54]:<56}{str(want):>6}{str(k):>10}{str(m):>8}{flag}")

print()
score("keywords", kw)
score("model", md)
