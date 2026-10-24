"""One JSON line per answer, safe to keep. Day 18.

WHY THE EXISTING TRACE WAS NOT ENOUGH. `app/verbose.py` prints a rich, readable report — and
only to **stderr**, only while `GENAI_VERBOSE_TRACE` is on, and only while somebody is
watching the terminal. A user who reports a bad answer from this morning leaves nothing to
look at. The tracker's done-when is "a mentor can diagnose poor AI answers", and diagnosis
after the fact had three terse INFO lines to work with.

WHAT MAKES IT SAFE TO KEEP, which is the other half of the same sentence: "without exposing
sensitive text in logs". Every value here is a NUMBER, an IDENTIFIER, or a short enum. No
chunk text, no answer text, no question, no quote, no filename. Those are the user's
documents, and a log line that helpfully included "the chunk we retrieved" turns the log into
a rotated copy of the corpus shipped to whoever can read it.

So this records WHAT HAPPENED, never WHAT WAS SAID:

    scores, counts, timings, token counts, model identity, which code path ran,
    which mechanism produced the citations, what the router decided

A chunk is identified by its UUID. Anyone who needs the text can look the row up in the
database, where access is already controlled — the log does not need to carry a second copy.

THE QUESTION IS RECORDED ONLY AS ITS LENGTH AND A HASH. The hash makes "this same question
was asked forty times" answerable without storing the question, which is the one aggregate
worth having and the one piece of user text it would be tempting to keep.

`tests/test_log_redaction.py` asserts all of this against the real path rather than trusting
it, and this module is covered by the same rule Spring's LogRedactionTest applies on its side.
"""
import hashlib
import json
import logging
from contextvars import ContextVar

#: THE JSON LINES LOGGER. Everything written through this name goes, verbatim and
#: unformatted, into logs/answers.jsonl — so nothing but a complete JSON object may ever be
#: logged here.
log = logging.getLogger("app.trace.answer")

#: Failures go somewhere ELSE, and that separation is load-bearing. The first version logged
#: its own exception through the line above, so a traceback was written into the JSON Lines
#: file — sixteen lines of it in the first hour of real traffic — and every consumer that
#: parses the file line-by-line broke on it. An error reporting channel that corrupts the
#: thing it reports on is worse than no error reporting.
errors = logging.getLogger(__name__)


def _question_fingerprint(question: str) -> str:
    """A stable short hash. Not reversible to the question, and not meant to be.

    Truncated to 12 hex characters: enough to group repeats in a corpus of thousands,
    short enough that nobody is tempted to treat it as an identifier for anything else.
    """
    return hashlib.sha256(question.encode("utf-8")).hexdigest()[:12]


#: The pipeline, in order. `stage` records how far a request got, so a failure says WHERE
#: rather than only THAT. These are the forks a person actually needs when an answer is bad:
#: nothing retrieved is a corpus problem, generation failing is a model problem, and a
#: parse failure is neither.
STAGES = (
    "config",            # which backend, is it configured at all
    "embedding_model",   # the encoder must be loaded before anything is embedded
    "generation_model",  # the generator must be loaded before anything is generated
    "retrieval",         # embed the question, search, threshold
    "generation",        # the model writes
    "parsing",           # the reply becomes an answer plus citations
    "complete",
)


_stage: ContextVar[str] = ContextVar("pipeline_stage", default="config")


def set_stage(stage: str) -> None:
    """Mark how far this request has got.

    A contextvar rather than a parameter threaded through the call chain: the handler is
    split across functions and the failure record is written by an `except` in the outer
    one, which cannot see a local variable in the inner. Same mechanism `app/trace.py` uses
    for the trace id, and reset per request by the default.
    """
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {STAGES}")
    _stage.set(stage)


def current_stage() -> str:
    return _stage.get()



#: THE PROMPT, when `GENAI_LOG_PROMPTS` is on. A ContextVar for the same reason the stage
#: is one: the prompt exists only inside `answering.answer_question`, and the trace record
#: is written afterwards by a caller that cannot see its locals. Same mechanism as
#: `generation.GenerationDetail`.
_prompt: ContextVar[tuple[str, str] | None] = ContextVar("rendered_prompt", default=None)

#: Full prompts, one block per request, written to logs/prompts.log. A SEPARATE file from
#: the JSON Lines one, because a 14,000-character prompt embedded in a JSON string is
#: readable by a parser and by nobody else.
prompts = logging.getLogger("app.trace.prompt")


def record_prompt(system: str, user: str) -> None:
    """Hold this request's prompt for the trace record. Does nothing unless enabled.

    Checked HERE rather than at the call site so there is exactly one place that decides,
    and so the caller cannot accidentally capture a prompt the operator did not ask for.
    """
    from app.config import settings

    if not settings.log_prompts:
        return
    _prompt.set((system, user))
    try:
        prompts.info(
            "\n%s\ntrace_id=%s\n--- SYSTEM ---\n%s\n--- USER ---\n%s\n",
            "=" * 96, _trace_id(), system, user)
    except Exception:  # noqa: BLE001 — a diagnostic must never break a served request
        errors.exception("could not write the prompt log")


def current_prompt() -> tuple[str, str] | None:
    return _prompt.get()

def record_failure(stage: str, backend: str, question: str, error: Exception,
                   detail=None) -> None:
    """A request that did NOT produce an answer. Day 18b.

    THIS IS THE RECORD THAT WAS MISSING, and its absence was the whole complaint. The
    success path was logged in detail and `record_answer` was the LAST line of the handler,
    after four separate exits that raise 503 — a model still loading, Gemini unconfigured,
    Gemini unavailable, and anything retrieval threw. So the requests most worth debugging
    were the exact ones that wrote nothing at all, and the log answered "what happened when
    it worked" while staying silent on "why did it fail".

    `stage` is the point of the whole thing: it separates "retrieval found nothing" from
    "the generation model is down" from "the cloud model is out of quota" — three failures
    that look identical to a user and need three different responses.

    Same redaction rule as the success record: the error MESSAGE is included because it is a
    system string written for an operator ("has used up its daily free quota"), never
    document text. The question is still only a hash and a length.
    """
    try:
        entry = {
            "trace_id": _trace_id(),
            "event": "failed",
            "stage": stage,
            "error_type": type(error).__name__,
            "error": str(error)[:300],
            "backend": backend,
            "question_sha": _question_fingerprint(question),
            "question_chars": len(question),
        }
        if detail is not None:
            entry |= {
                "attempts": detail.attempts,
                "http_status": detail.http_status,
                "thinking_tokens": detail.thinking_tokens,
                "finish_reason": detail.finish_reason,
            }
        log.info(json.dumps(entry, separators=(",", ":")))
    except Exception:  # noqa: BLE001
        errors.exception("could not record the failure trace")


def _trace_id() -> str:
    from app.trace import current_trace_id

    return current_trace_id()


def record_answer(response, question: str, backend: str) -> None:
    """Emit the trace line. Never raises.

    Observability must not be able to break the thing it observes. A malformed trace is a
    lost diagnostic; an exception here would be a 500 on a request that had already
    succeeded — the formatter taking down what it was formatting, which `verbose.py` already
    guards against for the same reason.
    """
    try:
        trace = response.trace
        from app.generation import current_detail

        detail = current_detail()
        verdict, suspect, reason = attribute_answer(
            retrieved=len(trace.retrieved),
            top_score=trace.retrieved[0].score if trace.retrieved else None,
            min_score=trace.min_score,
            answer_chars=len(response.answer.strip()),
            overlap=trace.grounding_overlap,
            rejected=trace.rejected_as_ungrounded,
            citations=len(response.citations),
            dropped_quotes=len(trace.dropped_quotes),
            parse_path=trace.parse_path,
        )
        entry = {
            # --- identity: what to grep for -------------------------------------
            "trace_id": trace.trace_id,
            # Every record carries one, so `event` partitions the file into answers and
            # failures without parsing the rest.
            "event": "answered",
            "stage": "complete",
            "question_sha": _question_fingerprint(question),
            "question_chars": len(question),

            # --- retrieval: did it find the right things? -----------------------
            "allowed_documents": trace.allowed_document_count,
            "candidates": trace.candidates_before_threshold,
            "collapsed_duplicates": trace.collapsed_duplicates,
            "anchor_expanded": trace.anchor_expanded,
            "best_rejected_score": trace.best_rejected_score,
            # COUNT, not the words. A typed word is user text and this file holds none.
            "spelling_corrections": len(trace.spelling_corrections),
            # The TERMS, not a count: these words exist in the corpus by definition, so
            # they are not user text the way a misspelling is, and which term fired is
            # the entire diagnostic value of the field.
            "rare_term_rescue": trace.rare_term_rescue,
            "filename_tiebreak": trace.filename_tiebreak,
            "retrieval_mode": trace.retrieval_mode,
            "retrieved": len(trace.retrieved),
            "min_score": trace.min_score,
            "top_k": trace.top_k,
            # Every score, in rank order. This is the field that makes a bad answer
            # diagnosable: a top score barely over the floor says "retrieval found nothing
            # good" and separates that from "the model ignored what it was given".
            "scores": [round(c.score, 4) for c in trace.retrieved],
            "chunk_ids": [str(c.chunk_id) for c in trace.retrieved],
            "document_ids": sorted({str(c.document_id) for c in trace.retrieved}),
            "retried_with_history": trace.retried_with_history,
            "history_turns": trace.history_turns_received,

            # --- generation: what produced the text? ----------------------------
            "backend": backend,
            "model": trace.generation_model,
            "model_revision": trace.generation_model_revision,
            "template": trace.prompt_template_version,
            "prompt_tokens": trace.prompt_tokens,
            "completion_tokens": trace.completion_tokens,
            "parse_path": trace.parse_path,
            # --- how the model behaved, not just how long it took ---------------
            # Gemini reasons before writing and those tokens come out of the SAME budget as
            # the answer; a cap consumed entirely by thinking produces an empty reply with
            # no error anywhere. `attempts` is 2 when the overload retry fired, which
            # separates "slow" from "retried".
            "thinking_tokens": detail.thinking_tokens,
            "finish_reason": detail.finish_reason,
            "attempts": detail.attempts,
            "http_status": detail.http_status,

            # --- the prompt, ONLY when GENAI_LOG_PROMPTS is on -------------------
            # Absent by default, and its absence is the redaction guarantee: this is the
            # one field in the record that carries document text. See config.log_prompts.
            **({"prompt": {"system": p[0], "user": p[1]}}
               if (p := current_prompt()) is not None else {}),

            # --- the conclusion, so nobody has to re-derive it ------------------
            # Provenance, not truth. See attribute_answer for exactly what this can and
            # cannot tell you.
            "verdict": verdict,
            "suspect": suspect,
            "suspect_reason": reason,

            # --- the guardrails: did any of them fire? --------------------------
            "outcome": response.outcome.value,
            "grounding_overlap": round(trace.grounding_overlap, 4),
            "rejected_as_ungrounded": trace.rejected_as_ungrounded,
            "quarantined_chunks": trace.quarantined_chunks,
            "unsupported_request": trace.unsupported_request is not None,

            # --- citations and tools --------------------------------------------
            "citations": len(response.citations),
            "citation_source": trace.citation_source,
            "dropped_quotes": len(trace.dropped_quotes),
            "routed_tool": trace.routed_tool,
            "routed_by": trace.routed_by,
            "proposals": len(response.proposals),

            # --- cost, in the only currency this service has --------------------
            "embed_ms": trace.embed_ms,
            "search_ms": trace.search_ms,
            "generate_ms": trace.generate_ms,
            "total_ms": trace.total_ms,
        }
        log.info(json.dumps(entry, separators=(",", ":")))
    except Exception:  # noqa: BLE001 — a diagnostic must never break a served request
        errors.exception(
            "could not record the answer trace; the answer itself was unaffected")


#: What the verdict can say. These describe the answer's PROVENANCE — whether its words
#: came from the retrieved documents — which is the closest thing to a hallucination
#: signal this service can honestly compute.
VERDICTS = ("grounded", "unverified", "ungrounded", "declined", "no_evidence", "weak_evidence")

#: Which part of the pipeline to look at first when the verdict is not `grounded`.
SUSPECTS = ("none", "retrieval", "generation", "parsing")


def attribute_answer(
    *,
    retrieved: int,
    top_score: float | None,
    min_score: float,
    answer_chars: int,
    overlap: float,
    rejected: bool,
    citations: int,
    dropped_quotes: int,
    parse_path: str,
) -> tuple[str, str, str]:
    """Name the verdict and the stage responsible. Day 18b. PURE — no I/O, no model.

    WHAT THIS IS FOR. A bad answer looks identical from the outside whatever caused it,
    and this project has now mistaken one cause for another three times in a week: a
    retrieval failure read as a broken cloud model, a prompt blamed for a chunk that never
    arrived, a parser blamed for LaTeX the documents never contained. The trace already
    held every number needed to tell them apart, scattered across a dozen fields. This puts
    the conclusion in one place so nobody has to re-derive it under pressure.

    WHAT IT CANNOT DO, stated here rather than discovered later. `overlap` is the fraction
    of the answer's words found in the chunks, so this measures PROVENANCE, NOT TRUTH:

      * `grounded` means the words came from the documents. It does NOT mean the answer is
        correct. A model that reads the right passage and states the opposite of it scores
        well here, and Qwen-0.5B has done exactly that on the refund rules.
      * A SHORT answer defeats the measure entirely — the denominator is chosen by the
        model, so a one-word answer present anywhere scores 1.000 (BACKLOG 21).
      * Function words inflate it in the other direction (BACKLOG 16).

    So read `unverified` as "nobody has checked this", never as "this is a lie", and read
    `grounded` as "it came from your documents", never as "it is right".

    The rules are ordered by how much they foreclose: nothing retrieved explains everything
    downstream, so it is asked first, and a weak top score is asked last because it is a
    hint rather than a cause.
    """
    if retrieved == 0:
        return ("no_evidence", "retrieval",
                "nothing cleared the score floor, so the model was given no documents")

    if answer_chars == 0:
        return ("declined", "generation",
                f"the model returned no answer although {retrieved} chunks were supplied")

    if rejected:
        return ("ungrounded", "generation",
                f"answer withheld: only {overlap:.0%} of its words appear in the chunks")

    barely = top_score is not None and top_score < min_score + 0.02
    if citations == 0:
        if barely:
            return ("unverified", "retrieval",
                    f"no citation resolved, and the best chunk scored {top_score:.3f} "
                    f"against a floor of {min_score:.2f} — the passages were probably wrong")
        if dropped_quotes:
            return ("unverified", "generation",
                    f"all {dropped_quotes} quotes the model gave failed to match any "
                    f"retrieved chunk")
        if parse_path != "json":
            return ("unverified", "parsing",
                    f"the reply was read as {parse_path} and carried no usable quotes")
        return ("unverified", "generation",
                "the model declared no quotes, so nothing could be traced to a source")

    if barely:
        return ("weak_evidence", "retrieval",
                f"answered and cited, but the best chunk scored {top_score:.3f} against a "
                f"floor of {min_score:.2f}")

    return ("grounded", "none", "")
