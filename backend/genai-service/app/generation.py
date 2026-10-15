"""Two generation backends behind one signature.

Everything else in this service — retrieval, quote-resolved citations, the grounding guard,
quarantine, the unsupported-request check — is model-agnostic and stays exactly as it is.
Only the step that turns a prompt into text differs, so that is the only thing swapped.

A backend is `(system, user) -> (reply_text, prompt_tokens, completion_tokens)`.

THE PRIVACY DIFFERENCE IS THE WHOLE POINT, and it is not a performance detail. Day 1
recorded "no document text leaves the machine" as a CONSEQUENCE of local models, not as a
requirement anyone imposed. Choosing `gemini` sends retrieved chunks — the user's private
documents — to Google. That is why the backend is chosen per request and reported in the
trace, rather than configured once and forgotten.
"""
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass

import httpx

from app.config import settings

log = logging.getLogger(__name__)

LOCAL = "local"
GEMINI = "gemini"


@dataclass
class GenerationDetail:
    """What the generation step did, beyond the three numbers the contract returns.

    WHY A CONTEXTVAR AND NOT A RETURN VALUE. A backend is
    `(system, user) -> (reply, prompt_tokens, completion_tokens)` and that signature is
    implemented by two backends, stubbed by a dozen tests and called from three benchmarks.
    Widening it to carry diagnostics would ripple through all of them to move information
    that only the trace reads. A contextvar is already how this service carries per-request
    data that is not part of a contract — see `app/trace.py` — and it is reset on every call
    so one request cannot inherit another's.

    Everything here is operational. No prompt, no reply, no document text.
    """

    backend: str = ""
    #: Gemini reasons internally before writing and those tokens come out of the SAME budget
    #: as the answer. A 500-token cap was once consumed entirely by thinking, producing an
    #: empty answer with no error anywhere. Invisible unless it is recorded.
    thinking_tokens: int = 0
    #: STOP, MAX_TOKENS, SAFETY. MAX_TOKENS with no text is the budget bug above.
    finish_reason: str | None = None
    #: 1 normally, 2 when the overload retry fired. Distinguishes "slow" from "retried".
    attempts: int = 0
    http_status: int | None = None


_detail: ContextVar[GenerationDetail] = ContextVar("generation_detail")


def start_detail(backend: str) -> GenerationDetail:
    """Begin recording for this request. Called before the backend runs."""
    detail = GenerationDetail(backend=backend)
    _detail.set(detail)
    return detail


def current_detail() -> GenerationDetail:
    """What the last generation reported, or an empty record if it never ran.

    Never raises: a request that failed before generation has nothing to report, and the
    trace needs a shape rather than an exception.
    """
    try:
        return _detail.get()
    except LookupError:
        return GenerationDetail()

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def local_generator(tokenizer, model):
    """Qwen2.5-0.5B on this machine's CPU. Measured: 4-8 tokens/s decode."""
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

        detail = current_detail()
        detail.attempts = 1
        # The local model has no thinking budget and no finish reason to report. Hitting the
        # cap is still worth recording: it is the difference between "the model stopped" and
        # "we cut it off", and a truncated reply is what produces salvaged_json downstream.
        detail.finish_reason = ("MAX_TOKENS"
                                if completion_tokens >= settings.generation_max_new_tokens
                                else "STOP")
        return reply, prompt_tokens, completion_tokens

    return generate


class GeminiUnavailable(RuntimeError):
    """Gemini could not answer. Distinct from a bug, so the caller can fail the request
    cleanly rather than treating a 503 as a contract violation."""


def gemini_generator(api_key: str, model_name: str):
    """Google's hosted Gemini.

    Four things learned by measuring this API before trusting it, each of which silently
    produces a wrong or empty answer if ignored:

    1. **Thinking tokens come out of the same budget.** Gemini 3.x reasons internally before
       writing, and `thoughtsTokenCount` counts against `maxOutputTokens`. A 500-token cap
       was consumed entirely by thinking — `finishReason: MAX_TOKENS`, and the answer field
       came back as the empty string with no error anywhere. The cap here is deliberately
       generous for that reason.
    2. **503 happens.** "This model is currently experiencing high demand" on a first call,
       succeeding seconds later. Retried once, like Spring retries this service.
    3. **Model names expire.** `gemini-2.0-flash` and `gemini-2.5-flash` both answer 404
       "no longer available to new users". The name is configuration, not a constant.
    4. **Parts can be multiple.** The text is joined across `content.parts`, not read from
       `parts[0]`, because a response carrying a thought signature splits them.
    """

    def generate(system: str, user: str) -> tuple[str, int, int]:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {
                "maxOutputTokens": settings.gemini_max_output_tokens,
                "temperature": settings.generation_temperature if settings.generation_do_sample else 0,
                "thinkingConfig": {"thinkingBudget": settings.gemini_thinking_budget},
            },
        }
        url = _GEMINI_URL.format(model=model_name)

        detail = current_detail()
        for attempt in (1, 2):
            detail.attempts = attempt
            started = time.perf_counter()
            try:
                response = httpx.post(
                    url,
                    # Header, not a query parameter: a key in a URL ends up in access logs,
                    # proxy logs and browser history.
                    headers={"x-goog-api-key": api_key},
                    json=payload,
                    timeout=settings.gemini_timeout_seconds,
                )
            except httpx.HTTPError as transport:
                raise GeminiUnavailable(f"could not reach Gemini: {type(transport).__name__}") from None

            detail.http_status = response.status_code

            if response.status_code == 503 and attempt == 1:
                log.warning("gemini is overloaded, retrying once")
                time.sleep(2)
                continue

            if response.status_code == 429:
                # Quota, not load, and the two need different words. Measured on the free
                # tier: the cap is GenerateRequestsPerDayPerProjectPerModel — per DAY, per
                # MODEL. "Try again in a moment" is false advice for a daily cap; waiting
                # will not help, and the fix is a different model or a paid plan.
                log.error("gemini quota exhausted for %s", model_name)
                raise GeminiUnavailable(
                    f"The cloud model '{model_name}' has used up its daily free quota. "
                    f"Switch to on-device, or configure a different Gemini model — the quota "
                    f"is per model."
                )
            if response.status_code == 503:
                raise GeminiUnavailable(
                    "The cloud model is overloaded right now. Try again shortly, "
                    "or switch to on-device."
                )
            if response.status_code != 200:
                # The body can echo the prompt back, so only the status is logged.
                log.error("gemini returned HTTP %d", response.status_code)
                raise GeminiUnavailable(
                    f"The cloud model refused the request (HTTP {response.status_code})."
                )

            body = response.json()
            candidate = (body.get("candidates") or [{}])[0]
            parts = candidate.get("content", {}).get("parts", [])
            reply = "".join(part.get("text", "") for part in parts)

            usage = body.get("usageMetadata", {})
            thoughts = usage.get("thoughtsTokenCount", 0)
            detail.thinking_tokens = int(thoughts)
            detail.finish_reason = candidate.get("finishReason")
            if candidate.get("finishReason") == "MAX_TOKENS" and not reply.strip():
                # Reported rather than returned as an empty answer: an empty string would
                # reach the grounding guard, score 0.0, and be recorded as a model failure
                # when it is actually a budget misconfiguration.
                raise GeminiUnavailable(
                    f"gemini spent its whole budget thinking ({thoughts} tokens) and wrote nothing"
                )

            log.info("gemini %s answered in %.1fs (thinking %d tokens)",
                     model_name, time.perf_counter() - started, thoughts)
            return (reply,
                    int(usage.get("promptTokenCount", 0)),
                    int(usage.get("candidatesTokenCount", 0)))

        raise GeminiUnavailable(
            "The cloud model is overloaded right now. Try again shortly, "
            "or switch to on-device."
        )

    return generate
