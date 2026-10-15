import logging
import time
from dataclasses import replace
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, status

from app.answering import answer_question
from app.config import settings
from app.generation import (
    GEMINI,
    GeminiUnavailable,
    current_detail,
    gemini_generator,
    start_detail,
)
from app.ingestion import Embedder
from app.intent import IntentRouter, proposals_for
from app.models_registry import registry
from app.observability import current_stage, record_answer, record_failure, set_stage
from app.prompts import template_for
from app.prompts.templates import SUMMARIZE_V1
from app.retrieval import document_opening
from app.retrieval import retrieve as run_retrieval
from app.schemas import (
    AnswerResponse,
    AnswerTrace,
    ErrorCode,
    ErrorResponse,
    ModelState,
    RetrievalRequest,
    RetrieveResponse,
    RetrieveTrace,
    SpellingCorrection,
    ToolName,
)
from app.trace import current_trace_id
from app.verbose import print_answer, print_request

log = logging.getLogger(__name__)
router = APIRouter(tags=["rag"])

# 501 was removed on Day 7: both endpoints here are implemented, and a published response
# code they can no longer return is a spec that lies to its only consumer. /ingest keeps
# its 501 because /ingest genuinely still returns one.
_ERRORS: dict[int | str, dict[str, Any]] = {
    503: {"model": ErrorResponse, "description": "A model is not loaded"},
}


@router.post(
    "/answer",
    response_model=AnswerResponse,
    responses=_ERRORS,
    summary="Grounded answer with citations and a diagnosable trace",
)
def answer(request: RetrievalRequest) -> AnswerResponse:
    """The product path.

    Three decisions here are made in code and never delegated to a 0.5B model:
      1. Whether there is enough context — scores are compared to min_score BEFORE the
         model is called. insufficient_context never reaches the LLM.
      2. Whether a citation is real — under qa-v2 the model quotes a SENTENCE and code
         resolves it to a chunk; an unresolvable quote is dropped into
         trace.dropped_quotes rather than guessed at.
      3. Whether a tool call runs — never here. This service PROPOSES; Spring's governance
         flow records a row for every decision including rejections, and only a human's
         approval has an effect.
      4. Which tool, if any, a message is asking for — decided by app.intent from the
         USER'S MESSAGE ONLY, never from retrieved text, so a poisoned document cannot
         forge a tool call.
    """
    started = time.perf_counter()
    # STAGE TRACKING. Every exit below writes a trace record, and `stage` is what makes a
    # failure diagnosable: it separates "nothing was retrieved" from "the generation model is
    # down" from "the cloud model is out of quota" — three failures that look identical to a
    # user and need three different answers. Before this, a failed request wrote NOTHING.
    set_stage("config")
    backend = "unknown"
    try:
        backend = _select_backend(request.model)
        return _answer(request, backend, started)
    except HTTPException as refused:
        detail = refused.detail if isinstance(refused.detail, dict) else {}
        record_failure(current_stage(), backend, request.question,
                       RuntimeError(str(detail.get("message", refused.detail))),
                       current_detail())
        raise
    except Exception as failure:
        # Anything unhandled: a database that went away mid-retrieval, a model that threw.
        # It becomes a 500 either way; the difference is that now there is a record of which
        # stage it died at.
        record_failure(current_stage(), backend, request.question, failure,
                       current_detail())
        raise


def _answer(request: RetrievalRequest, backend: str, started: float) -> AnswerResponse:
    """The product path. Split out so `answer` can own the stage tracking and the failure
    record without wrapping sixty lines in a try block."""
    if settings.verbose_trace:
        # Printed before the work starts: a request that takes a minute should show
        # something immediately rather than appearing hung.
        print_request(request.question, len(request.allowed_document_ids), backend)
    set_stage("embedding_model")
    embedder = _embedder()
    template = template_for(settings.prompt_template_version)
    start_detail(backend)

    if backend == GEMINI:
        assert settings.gemini_api_key is not None  # _select_backend guarantees this
        generate = gemini_generator(settings.gemini_api_key.get_secret_value(), settings.gemini_model)
        generation_model = settings.gemini_model
    else:
        set_stage("generation_model")
        tokenizer, model = _generator()
        generate = _make_generate(tokenizer, model)
        generation_model = settings.generation_model

    set_stage("retrieval")
    retrieval = run_retrieval(
        embed_query=embedder.embed_query,
        question=request.question,
        allowed_document_ids=request.allowed_document_ids,
        top_k=request.top_k,
        min_score=request.min_score,
        history=request.history,
    )

    # THE SUMMARISE PATH. Day 18b. Decided from the USER'S MESSAGE ALONE, exactly like the
    # tool routing below and for the same reason: a retrieved document must never be able
    # to change how it is itself read. `_route` sees `request.question` and nothing else.
    #
    # Why a second mode exists at all: "summarise the ai safety paper" is not a question
    # about a passage, and similarity retrieval has nothing to rank by when every chunk of
    # a document is equally about that document. Measured, the abstract of an 81-chunk
    # paper ranks 34th for "what is this paper about". See retrieval._OPENING_SQL.
    intent = _route(request.question)
    retrieval_mode = "similarity"
    if (
        intent is not None
        and intent.tool == ToolName.SUMMARIZE_DOCUMENT.value
        and retrieval.retrieved
        and retrieval.query_vector is not None
    ):
        # `retrieval.retrieved` being non-empty is the gate, and it is deliberate: the
        # anchor is a chunk that already cleared the allow-list and the score floor. A
        # request to summarise something the corpus does not contain retrieves nothing,
        # finds no anchor, and still ends in insufficient_context.
        opened, opened_texts = document_opening(
            retrieval.query_vector, retrieval.retrieved[0].document_id, request.top_k)
        if opened:
            retrieval = replace(retrieval, retrieved=opened, texts=opened_texts)
            template = SUMMARIZE_V1
            retrieval_mode = "document_summary"

    set_stage("generation")
    try:
        result = answer_question(
        retrieval=retrieval,
        question=request.question,
        template=template,
        generate=generate,
        history=request.history,
            include_raw=request.include_raw,
        )
    except GeminiUnavailable as unavailable:
        # Gemini is a remote dependency and can be overloaded or misconfigured. That is a
        # 503 "try again", not a 500 "this service is broken".
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": ErrorCode.MODEL_NOT_READY.value,
                "message": str(unavailable),
                "trace_id": current_trace_id(),
            },
        ) from None

    # Routing happens AFTER the answer and is independent of it: the decision is a function
    # of the user's message alone, so a poisoned document cannot forge a tool call. It is
    # also suppressed when the question was itself an unsupported request — telling a user
    # "I cannot do that" and offering them a tool in the same turn is a contradiction.
    if result.unsupported_request:
        intent, routed_by = None, "suppressed"
    else:
        # Already computed above to choose the retrieval mode; routed_by still reports how
        # the decision was reached. Routing remains a function of the message alone.
        routed_by = intent.decided_by if intent else "failed"
    proposals = (
        proposals_for(request.question, intent, retrieval.retrieved) if intent else []
    )

    response = AnswerResponse(
        outcome=result.outcome,
        answer=result.answer,
        citations=result.citations,
        proposals=proposals,
        trace=AnswerTrace(
            trace_id=current_trace_id(),
            retrieved=retrieval.retrieved,
            top_k=request.top_k,
            min_score=request.min_score,
            candidates_before_threshold=retrieval.candidates_before_threshold,
            anchor_expanded=retrieval.anchor_expanded,
            best_rejected_score=retrieval.best_rejected_score,
            spelling_corrections=[SpellingCorrection(typed=t, used=u)
                                  for t, u in retrieval.spelling_corrections],
            retrieval_mode=retrieval_mode,
            collapsed_duplicates=retrieval.collapsed_duplicates,
            allowed_document_count=len(request.allowed_document_ids),
            embedding_model=settings.embedding_model,
            embedding_model_revision=settings.embedding_model_revision,
            query_prefix_applied=True,
            history_turns_received=len(request.history),
            retried_with_history=retrieval.retried_with_history,
            embed_ms=retrieval.embed_ms,
            search_ms=retrieval.search_ms,
            generation_backend=backend,
            generation_model=generation_model,
            generation_model_revision=(
                "hosted" if backend == GEMINI else settings.generation_model_revision
            ),
            # The template ACTUALLY used, read back from the rendered prompt — not
            # settings.prompt_template_version echoed. If a future change makes those two
            # disagree, the trace should be the thing that says so.
            prompt_template_version=result.template_version,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            generate_ms=result.generate_ms,
            unsupported_request=result.unsupported_request,
            quarantined_chunks=result.quarantined_chunks,
            quarantine_reasons=result.quarantine_reasons,
            parse_path=result.parse_path,
            raw_model_reply=result.raw_model_reply,
            grounding_overlap=result.grounding_overlap,
            rejected_as_ungrounded=result.rejected_as_ungrounded,
            dropped_quotes=result.dropped_quotes,
            citation_source=result.citation_source,
            routed_tool=intent.tool if intent else None,
            routed_by=routed_by,
            routing_confidence=round(intent.confidence, 4) if intent else None,
            total_ms=int((time.perf_counter() - started) * 1000),
        ),
    )

    # ALWAYS, not only under verbose_trace. The readable report is a demo aid that needs
    # someone watching; this is the record that makes a bad answer diagnosable tomorrow.
    # It carries no document text, no answer and no question — see app/observability.py.
    record_answer(response, request.question, backend)

    if settings.verbose_trace:
        _print_verbose(response)
    return response


def _route(question: str):
    """The tool decision, or None if the router could not be fitted.

    Never raises and never 503s. A question is answerable whether or not an action could be
    proposed from it, and a classifier that failed to fit must cost the user nothing beyond
    the two tools that need it.
    """
    router = registry.intent_router
    if router is None:
        # Keywords still work without the classifier, and they are the half with measured
        # zero false positives. Degrading to them beats proposing nothing at all.
        router = IntentRouter(classifier=None)
    try:
        return router.route(question)
    except Exception:  # noqa: BLE001
        log.exception("intent routing failed; this turn proposes nothing")
        return None


def _chunk_lookup(chunk_id: str) -> tuple[str, int | None, str]:
    """chunk id -> (filename, page, text), straight from the rows Spring wrote.

    Only called when verbose tracing is on, so a demonstration costs one small query per
    chunk and an ordinary request costs nothing.
    """
    import psycopg

    with psycopg.connect(settings.dsn) as conn:
        row = conn.execute(
            "select d.filename, c.page, c.text from document_chunks c "
            "join documents d on d.id = c.document_id where c.id = %s", (chunk_id,)).fetchone()
    return row if row is not None else ("(chunk no longer exists)", None, "")


def _print_verbose(response: AnswerResponse) -> None:
    try:
        print_answer(response, _chunk_lookup)
    except Exception:  # noqa: BLE001 — a demonstration aid must never break a request
        log.exception("verbose trace failed; the answer itself was unaffected")


def _embedder() -> Embedder:
    """Built per request from the already-loaded model. Cheap: it wraps, never loads.

    Readiness is checked on the EMBEDDING model alone, not registry.is_ready. Retrieval
    does not use the generator, and refusing to retrieve because a model this endpoint
    never calls is still loading would be a self-inflicted outage — /health/ready is the
    place that speaks for both.
    """
    model = registry.embedder
    # Read the handle ONCE and test the handle, not just the state flag. The state and the
    # attribute are set under the same lock but read here without it, so testing the flag
    # alone would leave a window where READY is visible before `embedder` is. This also
    # gives the type checker the narrowing it correctly demanded.
    if registry.embedding_state is not ModelState.READY or model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": ErrorCode.MODEL_NOT_READY.value,
                "message": registry.status_message(),
                "trace_id": current_trace_id(),
            },
        )
    return Embedder(
        # np.asarray, not .tolist() directly: SentenceTransformer.encode is typed as
        # returning Tensor | list[Tensor] | ndarray depending on its arguments, and only
        # some of those have .tolist(). Normalising the type here is the honest fix.
        encode=lambda texts, bs: np.asarray(
            model.encode(
                list(texts), batch_size=bs, normalize_embeddings=True, show_progress_bar=False
            )
        ).tolist(),
        dim=settings.embedding_dim,
        model=settings.embedding_model,
        revision=settings.embedding_model_revision,
    )


def _generator():
    """The generation model and its tokenizer, or 503.

    Checked separately from the embedding model and for the same reason `_embedder` checks
    only its own: /answer genuinely needs both, /retrieve needs neither generator nor
    503 from one. The handle is read once and tested, not inferred from the state flag.
    """
    tokenizer, model = registry.tokenizer, registry.generator
    if registry.generation_state is not ModelState.READY or tokenizer is None or model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": ErrorCode.MODEL_NOT_READY.value,
                "message": registry.status_message(),
                "trace_id": current_trace_id(),
            },
        )
    return tokenizer, model


def _select_backend(requested: str | None) -> str:
    """Which backend answers, and whether it can.

    Falling back to local when Gemini is unconfigured would be the wrong kindness: the
    caller asked for a backend that sends data off the machine, and quietly serving a
    different one hides that the choice did nothing. A 503 naming the reason is honest.
    """
    backend = requested or settings.default_generation_backend
    if backend == GEMINI and settings.gemini_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": ErrorCode.MODEL_NOT_READY.value,
                "message": "Gemini was requested but no API key is configured",
                "trace_id": current_trace_id(),
            },
        )
    return backend


def _make_generate(tokenizer, model):
    """Returns (system, user) -> (reply_text, prompt_tokens, completion_tokens).

    Decoding settings come from config, which defaults to GREEDY. That is a citation
    decision, not a style one: qa-v2 resolves citations by matching the model's quote back
    to chunk text, so sampling that perturbs a single word can turn a resolvable citation
    into a dropped one. Day 7 measures both rather than inheriting benchmark 08's habit.

    The document text lives in the USER message, never the system message — retrieved
    chunks are user-uploaded content, i.e. untrusted input. Day 12 hardens this; today's
    job is to make sure Day 12 is a change rather than a rewrite.
    """
    import torch

    def generate(system: str, user: str) -> tuple[str, int, int]:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer([prompt], return_tensors="pt")
        prompt_tokens = int(inputs.input_ids.shape[1])

        kwargs = {
            "max_new_tokens": settings.generation_max_new_tokens,
            "do_sample": settings.generation_do_sample,
            "pad_token_id": tokenizer.eos_token_id,
        }
        if settings.generation_do_sample:
            kwargs |= {
                "temperature": settings.generation_temperature,
                "top_p": settings.generation_top_p,
                "top_k": settings.generation_top_k,
            }

        with torch.no_grad():
            out = model.generate(**inputs, **kwargs)

        completion_tokens = int(out.shape[1]) - prompt_tokens
        reply = tokenizer.decode(out[0][prompt_tokens:], skip_special_tokens=True)
        return reply, prompt_tokens, completion_tokens

    return generate


@router.post(
    "/retrieve",
    response_model=RetrieveResponse,
    responses=_ERRORS,
    summary="Retrieval only, no generation. For evaluation, not for the product",
)
def retrieve(request: RetrievalRequest) -> RetrieveResponse:
    """Exists so a bad answer can be bisected into "retrieval was wrong" or "generation
    was wrong", and so Day 13's golden questions can test retrieval without paying for
    generation. The product path does not call this."""
    started = time.perf_counter()
    embedder = _embedder()

    outcome = run_retrieval(
        embed_query=embedder.embed_query,
        question=request.question,
        allowed_document_ids=request.allowed_document_ids,
        top_k=request.top_k,
        min_score=request.min_score,
        history=request.history,
    )

    return RetrieveResponse(
        retrieved=outcome.retrieved,
        trace=RetrieveTrace(
            trace_id=current_trace_id(),
            retrieved=outcome.retrieved,
            top_k=request.top_k,
            min_score=request.min_score,
            candidates_before_threshold=outcome.candidates_before_threshold,
            anchor_expanded=outcome.anchor_expanded,
            best_rejected_score=outcome.best_rejected_score,
            spelling_corrections=[SpellingCorrection(typed=t, used=u)
                                  for t, u in outcome.spelling_corrections],
            collapsed_duplicates=outcome.collapsed_duplicates,
            allowed_document_count=len(request.allowed_document_ids),
            embedding_model=settings.embedding_model,
            embedding_model_revision=settings.embedding_model_revision,
            # Not a constant: embed_query is the only path that applies it, and this
            # endpoint is the only caller of embed_query. If that ever stops being true
            # the trace should be the thing that says so.
            query_prefix_applied=True,
            history_turns_received=len(request.history),
            retried_with_history=outcome.retried_with_history,
            embed_ms=outcome.embed_ms,
            search_ms=outcome.search_ms,
            total_ms=int((time.perf_counter() - started) * 1000),
        ),
    )
