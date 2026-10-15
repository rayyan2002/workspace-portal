"""Day 10: can the model infer a task priority, or should Spring keep hardcoding 'medium'?

schemas.py states the goal: "priority: Matches TaskPriority. Month 2 hardcoded 'medium';
Month 3 infers it." This measures whether inferring it is actually better than not.

THE BASELINE MATTERS. Spring returns "medium" for everything today, so "always medium"
already scores 3/9 on this set. A model that scores 3/9 has added 7 seconds and learned
nothing; it has to beat the constant to be worth wiring.

The labels are a human judgement about deliberately unambiguous phrasing — "urgent",
"before the demo tomorrow", "when you get a chance". Where a reasonable person could argue,
the case does not belong in the set.
"""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from app.config import settings
from app.prompts import parse_proposal
from app.prompts.templates import _FENCE_RULE, PromptTemplate

EXTRACT = PromptTemplate(
    version="extract-v1",
    numbered=False,
    system=(
        "The user has asked for a task to be tracked. Produce its details.\n\n"
        f"{_FENCE_RULE}\n\n"
        "Reply with one JSON object and nothing else, containing:\n"
        '- "tool": create-task\n'
        '- "title": a short task title taken from the message\n'
        '- "priority": how urgent the message says it is'
    ),
)

CASES = [
    ("fix the login bug immediately, it is blocking the demo", "high"),
    ("urgent: the runway inspection report is overdue", "high"),
    ("we need the finance summary before tomorrow's board meeting", "high"),
    ("when you get a chance, tidy up the ADBMS notes", "low"),
    ("sometime next month we should archive the old logs", "low"),
    ("no rush, but the README could use a refresh", "low"),
    ("create a task to review the runway inspection findings", "medium"),
    ("add a task for the demo rehearsal", "medium"),
    ("note down that the quarterly report needs a second look", "medium"),
]

tok = AutoTokenizer.from_pretrained(settings.generation_model, revision=settings.generation_model_revision)
model = AutoModelForCausalLM.from_pretrained(
    settings.generation_model, revision=settings.generation_model_revision, torch_dtype=torch.float32)
model.eval()

VALID = {"low", "medium", "high"}


def infer(message: str) -> tuple[str | None, str | None]:
    r = EXTRACT.render([], message)
    chat = [{"role": "system", "content": r.system}, {"role": "user", "content": r.user}]
    ids = tok([tok.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)], return_tensors="pt")
    n = int(ids.input_ids.shape[1])
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=80, do_sample=False, pad_token_id=tok.eos_token_id)
    reply = tok.decode(out[0][n:], skip_special_tokens=True)

    # parse_proposal owns the tool/title contract; priority is read here the same lenient way
    # and validated strictly against TaskPriority.
    import json
    import re
    parsed = parse_proposal(reply, chunk_count=0)
    priority = None
    match = re.search(r'"priority"\s*:\s*"([^"]*)"', reply)
    if match and match.group(1).strip().lower() in VALID:
        priority = match.group(1).strip().lower()
    del json
    return parsed.title, priority


print(f"{'message':<56}{'want':>8}{'model':>10}{'title'!s:>4}")
print("-" * 92)
model_right = baseline_right = 0
unusable = 0
for message, want in CASES:
    title, priority = infer(message)
    model_right += priority == want
    baseline_right += want == "medium"
    if priority is None:
        unusable += 1
    mark = "" if priority == want else "  <-"
    print(f"{message[:54]:<56}{want:>8}{str(priority):>10}   {(title or '(none)')[:28]}{mark}")

n = len(CASES)
print("\n" + "=" * 92)
print(f"  model           : {model_right}/{n} correct   ({unusable} unusable/invalid)")
print(f"  always 'medium' : {baseline_right}/{n} correct   <- what Spring does today, for free")
verdict = "WORTH WIRING" if model_right > baseline_right else "NOT worth 7s — the constant is as good"
print(f"\n  verdict: {verdict}")
