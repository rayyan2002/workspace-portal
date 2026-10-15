"""Day 14/15: tool selection accuracy and false positives, as a number.

The tests assert; this reports. Both read evaluation/tool_cases.json, so there is one set
of cases and two consumers of it.

THE DUPLICATION THIS FILE USED TO CONTAIN IS GONE. Until Day 14b the rules below were
REIMPLEMENTED here in Python — a copy of a Java trigger list, carrying a note admitting it
was a copy and naming the Spring test as authoritative if they ever diverged. A comment is
not a mechanism. The router now lives in app/intent.py, in the one language that holds the
encoder, and this script imports it:

    from app.intent import IntentRouter, keyword_route

So "what the benchmark measures" and "what the product does" are the same code. The only
thing left to choose is whether to pay for the encoder.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.intent import IntentRouter, keyword_route  # noqa: E402

CASES = json.loads((ROOT / "evaluation" / "tool_cases.json").read_text())


def fitted_router() -> IntentRouter:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    from app.config import settings

    model = SentenceTransformer(settings.embedding_model,
                                revision=settings.embedding_model_revision, device="cpu")
    return IntentRouter.fit(lambda texts: np.asarray(model.encode(
        list(texts), batch_size=32, normalize_embeddings=True, show_progress_bar=False)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keywords-only", action="store_true",
                    help="skip the encoder and measure the trigger rules alone, as the "
                         "router did before Day 14b")
    args = ap.parse_args()

    # One name, one definition. Two `def route` in exclusive branches reads fine and is a
    # redeclaration to a type checker, which cannot know the branches are exclusive.
    if args.keywords_only:
        router_name = "keyword rules only (no encoder loaded)"
        router = None
    else:
        router = fitted_router()
        router_name = "app.intent.IntentRouter — keyword rules + fitted classifier"

    def route(message):
        if router is None:
            return keyword_route(message), "keywords"
        intent = router.route(message)
        return intent.tool, intent.decided_by

    print(f"ROUTER: {router_name}\n")
    print(f"{'message':<56}{'expected':<20}{'routed':<20}{'by':<12}")
    print("-" * 110)

    tp = fp = fn = wrong = 0
    by_half: dict[str, int] = {}
    for case in CASES["routing"]:
        want = case["expect"]
        got, decided_by = route(case["message"])
        if got is not None:
            by_half[decided_by] = by_half.get(decided_by, 0) + 1

        if want is None and got is not None:
            fp += 1
            flag = "  <- FALSE POSITIVE"
        elif want is not None and got is None:
            fn += 1
            flag = "  <- missed"
        elif want is not None and got != want:
            wrong += 1
            flag = "  <- WRONG TOOL"
        else:
            tp += want is not None
            flag = ""
        print(f"{case['message'][:54]:<56}{(want or '(none)'):<20}{(got or '(none)'):<20}"
              f"{decided_by if got else '':<12}{flag}")

    total = len(CASES["routing"])
    correct = total - fp - fn - wrong
    print(f"\n  selection accuracy   : {correct}/{total}")
    print(f"  proposed correctly   : {tp}")
    print(f"  FALSE POSITIVES      : {fp}   <- the expensive error")
    print(f"  missed               : {fn}")
    print(f"  wrong tool           : {wrong}")
    print(f"  trap cases included  : {sum(1 for c in CASES['routing'] if 'trap' in c)}")
    print(f"  decided by           : {by_half or '(nothing proposed)'}")

    # Day 14 printed a "NOT MEASURED" section here listing the cases marked
    # unreachable_today, because the router could only ever emit create-task and the other
    # two tools' selection accuracy was undefined rather than good. Day 14b made them
    # reachable, so every case in the file is now scored above and the section is gone.
    reachable = [c for c in CASES["routing"] if c["expect"] not in (None, "create-task")]
    print(f"\n  non-create-task cases now scored: {len(reachable)} "
          f"({', '.join(sorted({c['expect'] for c in reachable}))})")
    print(f"  validation cases     : {len(CASES['validation'])} "
          f"({sum(1 for c in CASES['validation'] if c['expect_tool'] is None)} exercise a failure path)")

    print("\n  COMPARE: python benchmarks/22_tool_evaluation.py --keywords-only")
    print("  That is the router this replaced. It cannot emit summarize-document or")
    print("  lookup-knowledge at all, so both of those cases are structural misses for it.")


if __name__ == "__main__":
    main()
