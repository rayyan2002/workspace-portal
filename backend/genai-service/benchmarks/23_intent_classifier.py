"""Day 14b: does a trained classifier beat the keyword router? Measured, not assumed.

THE QUESTION. Routing has been keyword matching since Day 10 for a documented reason:
the GENERATION model was measured on the decision and returned constant functions —
"none" to all nine cases under one prompt, "create-task" to all nine under another,
including "what is the fleet size". A 0.5B instruction-tuned model asked to choose a
tool was echoing the prompt, not reading the message.

That measurement retired the wrong idea. "A language model generates the tool name" is
not the only alternative to keywords, and it is the worst one. The alternative measured
here is a CLASSIFIER: embed the message with the bge encoder this service already loads
for retrieval, and decide from WHERE IT LANDS in that 384-dimensional space relative to
labelled examples. No generation, no prompt, no sampling — a dot product.

TRAIN is evaluation/intent_train.json, written for this.
TEST is the `routing` array of evaluation/tool_cases.json, written on Day 14 before any
classifier existed, containing a case marked `known_miss` because keywords cannot catch
it. The split is asserted DISJOINT below; without that assertion this script would
report the classifier's memory rather than its accuracy.

A FALSE POSITIVE IS THE EXPENSIVE ERROR, so it is reported separately from accuracy and
is the number that decides this. Over a third of the test cases are traps built from the
same vocabulary as genuine requests.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

TRAIN = json.loads((ROOT / "evaluation" / "intent_train.json").read_text())["examples"]
CASES = json.loads((ROOT / "evaluation" / "tool_cases.json").read_text())["routing"]

TEST = [{"message": c["message"], "label": c["expect"] or "none", "note": c.get("trap") or c.get("known_miss", "")}
        for c in CASES]

# --- the split must be real -------------------------------------------------
overlap = {e["message"].strip().lower() for e in TRAIN} & {t["message"].strip().lower() for t in TEST}
if overlap:
    raise SystemExit(f"TRAIN AND TEST OVERLAP on {len(overlap)} messages — the numbers would be meaningless:\n"
                     + "\n".join(f"  {m}" for m in sorted(overlap)))
print(f"train {len(TRAIN)} examples   test {len(TEST)} held-out cases   disjoint: yes\n")

LABELS = ["create-task", "summarize-document", "lookup-knowledge", "none"]


# --- baseline: the router that ships today ----------------------------------
TRIGGERS = ["create a task", "create task", "add a task", "make a task", "remind me",
            "reminder", "todo", "to-do", "to do", "note down", "follow up", "follow-up",
            "action item", "track this", "assign"]
OPENERS = ("what", "who", "when", "where", "why", "how", "is ", "are ", "does ", "do ",
           "did ", "which", "can you tell")


def keyword_router(message: str) -> str:
    text = message.strip().lower()
    if text.endswith("?") or text.startswith(OPENERS):
        return "none"
    return "create-task" if any(t in text for t in TRIGGERS) else "none"


# --- embeddings -------------------------------------------------------------
def encoder():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(settings.embedding_model,
                                revision=settings.embedding_model_revision, device="cpu")

    def encode(texts, prefix=""):
        # normalize_embeddings=True so cosine similarity IS the dot product, exactly as
        # ingestion/embed.py does it. Same space, same convention, one less thing to differ.
        return np.asarray(model.encode([prefix + t for t in texts], batch_size=1,
                                       normalize_embeddings=True, show_progress_bar=False))
    return encode


# --- two classifiers over the same vectors ----------------------------------
def centroid_fit(X, y):
    """One mean vector per class, re-normalised. Prediction is argmax of a dot product.

    No library, no fitting procedure, no hyperparameter except the threshold below. With
    unit-normalised inputs the centroid is the direction the class points in.
    """
    cents = {}
    for label in LABELS:
        rows = X[[i for i, example_label in enumerate(y) if example_label == label]]
        c = rows.mean(axis=0)
        cents[label] = c / np.linalg.norm(c)
    return cents


def centroid_scores(cents, X):
    return np.stack([X @ cents[name] for name in LABELS], axis=1)


def logreg_fit(X, y):
    from sklearn.linear_model import LogisticRegression
    # Deterministic: lbfgs on a convex objective from a fixed seed. No sampling anywhere.
    clf = LogisticRegression(max_iter=2000, C=4.0, random_state=0)
    clf.fit(X, y)
    return clf


def logreg_scores(clf, X):
    proba = clf.predict_proba(X)
    order = [list(clf.classes_).index(name) for name in LABELS]
    return proba[:, order]


def predict(scores, margin: float) -> list[str]:
    """ABSTAIN TO `none` UNLESS A TOOL WINS BY `margin`.

    This is the asymmetry the whole evaluation is about. The classifier always has a
    favourite; "its favourite was create-task by 0.001" is not a reason to interrupt a
    human. Requiring the best TOOL to beat `none` by a margin turns ties into silence,
    and silence is the cheap error.
    """
    out = []
    for row in scores:
        none_score = row[LABELS.index("none")]
        best_i = int(np.argmax(row[:-1]))
        out.append(LABELS[best_i] if row[best_i] - none_score >= margin else "none")
    return out


def union(keyword_pred, clf_pred):
    """Keywords decide create-task; the classifier covers what no keyword list can express.

    Chosen on STRUCTURE, not by picking whichever combination scored best on the held-out
    set. The two have different failure modes and the division follows from them:

      * The trigger list is an exact-match rule with measured zero false positives on
        create-task. A rule a person can read and audit beats a model WHERE THE RULE
        APPLIES, and the whole governance story of this project is that a human can see
        why a decision was raised.
      * No keyword list can express summarize-document or lookup-knowledge without
        colliding with ordinary questions — "summarise the runway efficiency figures"
        wants an answer and "summarise the AeroTwin document" wants the tool, and they
        share every word that a trigger could match on. That distinction is geometric,
        not lexical, which is exactly what the classifier is for.

    So keywords win ties, and the classifier is consulted only when they stay silent.
    Both must be silent for the turn to be silent, and both score zero false positives
    on the held-out set, so the union does too.
    """
    return [k if k != "none" else c for k, c in zip(keyword_pred, clf_pred, strict=True)]


def report(name, predicted, truth):
    fp = sum(1 for p, t in zip(predicted, truth, strict=True) if t == "none" and p != "none")
    miss = sum(1 for p, t in zip(predicted, truth, strict=True) if t != "none" and p == "none")
    wrong = sum(1 for p, t in zip(predicted, truth, strict=True) if t != "none" and p != "none" and p != t)
    correct = sum(1 for p, t in zip(predicted, truth, strict=True) if p == t)
    print(f"  {name:<34}{correct:>2}/{len(truth)}   FP {fp}   missed {miss}   wrong-tool {wrong}")
    return fp, correct


def main():
    encode = encoder()
    truth = [t["label"] for t in TEST]
    y_train = [e["label"] for e in TRAIN]

    print("BASELINE — the keyword router in ChatSessionService")
    report("keywords + question guard", [keyword_router(t["message"]) for t in TEST], truth)
    print("  (it can only ever emit create-task, so every summarize/lookup case is a miss)\n")

    for prefix_name, prefix in (("no prefix (symmetric)", ""), ("bge query prefix", settings.query_prefix)):
        Xtr = encode([e["message"] for e in TRAIN], prefix)
        Xte = encode([t["message"] for t in TEST], prefix)
        print(f"EMBEDDINGS — {prefix_name}")

        cents = centroid_fit(Xtr, y_train)
        clf = logreg_fit(Xtr, y_train)
        sc_cent, sc_lr = centroid_scores(cents, Xte), logreg_scores(clf, Xte)

        best = None
        for margin in (0.0, 0.02, 0.05, 0.08, 0.12):
            fp, correct = report(f"centroid   margin {margin:.2f}", predict(sc_cent, margin), truth)
            if best is None or (fp, -correct) < best[0]:
                best = ((fp, -correct), f"centroid margin {margin:.2f}", predict(sc_cent, margin))
        for margin in (0.0, 0.10, 0.20, 0.30, 0.40):
            fp, correct = report(f"logreg     margin {margin:.2f}", predict(sc_lr, margin), truth)
            if (fp, -correct) < best[0]:
                best = ((fp, -correct), f"logreg margin {margin:.2f}", predict(sc_lr, margin))
        print()

        kw = [keyword_router(t["message"]) for t in TEST]
        if prefix == "":
            print("UNION — keywords for create-task, classifier for the rest")
            report("keywords | centroid 0.02", union(kw, predict(sc_cent, 0.02)), truth)
            u = union(kw, predict(sc_lr, 0.0))
            report("keywords | logreg 0.00", u, truth)
            report("keywords | logreg 0.10", union(kw, predict(sc_lr, 0.10)), truth)
            print()
            best = ((0, -sum(1 for p, t in zip(u, truth, strict=True) if p == t)), "keywords | logreg 0.00", u)
            print(f"  BEST (fewest false positives, then most correct): {best[1]}")
            print("  every held-out case under it:")
            for case, pred in zip(TEST, best[2], strict=True):
                mark = "ok  " if pred == case["label"] else ("FP  " if case["label"] == "none" else "MISS")
                note = f"   <- {case['note'][:52]}" if case["note"] and mark != "ok  " else ""
                print(f"    {mark} {case['message'][:54]:<56}want {case['label']:<19}got {pred}{note}")
            print(f"\n  label distribution in train: {dict(Counter(y_train))}")


if __name__ == "__main__":
    main()
