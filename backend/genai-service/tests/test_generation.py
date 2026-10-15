"""Day 15: both generation backends, with NO model and NO network.

`app/generation.py` was the least-tested module in the service — **19% covered** — and it
is the one place a wrong answer can be produced silently rather than loudly. Its docstring
records four Gemini behaviours learned by measuring the API, each of which "silently
produces a wrong or empty answer if ignored". Every one of those four is now a test, because
a behaviour recorded only in prose is a behaviour nothing re-checks.

HOW THE MODELS ARE FAKED. The local backend gets a tokenizer and model object that satisfy
exactly the interface `local_generator` uses, so the real decode arithmetic runs against
real tensors without loading 1.5GB of weights. The Gemini backend gets `httpx.post`
monkeypatched, so the real request-building, retry and error-classification code runs with
no key, no quota and no network.

This is the tracker's "mocked LLM calls" and "failure simulation", and the reason it
matters here specifically: Gemini's failures are the ones a user actually meets. A 429 is a
DAILY cap and "try again in a moment" is false advice for it — that distinction exists in
one `if` and nothing tested it until now.
"""
import httpx
import pytest

from app import generation
from app.config import settings
from app.generation import GEMINI, LOCAL, GeminiUnavailable, gemini_generator, local_generator

# --- the local backend ------------------------------------------------------

class _Batch(dict):
    """Stands in for transformers' BatchEncoding: a mapping that also exposes attributes.

    Both forms are used by the code under test — `inputs.input_ids.shape[1]` reads an
    attribute, and `model.generate(**inputs)` unpacks it as a mapping — so a fake that
    supports only one of them would pass for the wrong reason.
    """

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as missing:
            raise AttributeError(name) from missing


class _FakeTokenizer:
    eos_token_id = 7

    def __init__(self, prompt_tokens=11, reply="A grounded answer."):
        self._prompt_tokens = prompt_tokens
        self._reply = reply
        self.chat_template_calls = []

    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        self.chat_template_calls.append(messages)
        return "<|im_start|>rendered<|im_end|>"

    def __call__(self, texts, return_tensors) -> "_Batch":
        import torch

        return _Batch(input_ids=torch.zeros((1, self._prompt_tokens), dtype=torch.long))

    def decode(self, ids, skip_special_tokens):
        assert skip_special_tokens, "special tokens would reach the user's screen"
        return self._reply


class _FakeModel:
    def __init__(self, new_tokens=9):
        self._new_tokens = new_tokens
        # Typed and empty rather than None: every test reads kwargs after a generate call,
        # and `None` made each of those reads a type error about a case that cannot happen.
        self.kwargs: dict[str, object] = {}

    def generate(self, input_ids, **kwargs):
        """`input_ids` is REQUIRED, not an optional keyword.

        It was `input_ids=None`, which made `input_ids.shape` a type error about a call that
        cannot happen — the code under test always passes it. Requiring it says so.
        """
        import torch

        self.kwargs = kwargs
        return torch.zeros((1, input_ids.shape[1] + self._new_tokens), dtype=torch.long)


def test_the_local_backend_returns_text_and_both_token_counts():
    tokenizer, model = _FakeTokenizer(prompt_tokens=11, reply="A grounded answer."), _FakeModel(9)

    reply, prompt_tokens, completion_tokens = local_generator(tokenizer, model)("sys", "usr")

    assert reply == "A grounded answer."
    assert prompt_tokens == 11
    # Derived by subtraction from the output width, not reported by the model. If that
    # arithmetic inverts, the trace reports a negative completion count and nothing else
    # notices — the number is only ever read by a human.
    assert completion_tokens == 9


def test_the_system_and_user_messages_stay_in_their_own_roles():
    """The document text lives in the USER message, never the system message.

    Retrieved chunks are user-uploaded content, i.e. untrusted input. Day 12's quarantine
    assumes this separation; if the two were concatenated into one system prompt, an
    injected instruction would arrive with system authority.
    """
    tokenizer, model = _FakeTokenizer(), _FakeModel()

    local_generator(tokenizer, model)("SYSTEM RULES", "CONTEXT AND QUESTION")

    [messages] = tokenizer.chat_template_calls
    assert messages == [
        {"role": "system", "content": "SYSTEM RULES"},
        {"role": "user", "content": "CONTEXT AND QUESTION"},
    ]


def test_decoding_is_greedy_and_carries_no_sampling_knobs(monkeypatch):
    """Greedy is a CITATION decision, not a style one: qa-v2 resolves citations by matching
    the model's quote back to chunk text, so sampling that perturbs a single word turns a
    resolvable citation into a dropped one. Passing temperature with do_sample=False also
    makes transformers warn, which is how this was noticed."""
    monkeypatch.setattr(settings, "generation_do_sample", False)
    model = _FakeModel()

    local_generator(_FakeTokenizer(), model)("sys", "usr")

    assert model.kwargs["do_sample"] is False
    assert "temperature" not in model.kwargs
    assert "top_p" not in model.kwargs
    assert "top_k" not in model.kwargs
    assert model.kwargs["max_new_tokens"] == settings.generation_max_new_tokens
    assert model.kwargs["pad_token_id"] == 7, "the tokenizer's eos, or generation warns and pads wrong"


def test_sampling_knobs_appear_only_when_sampling_is_on(monkeypatch):
    monkeypatch.setattr(settings, "generation_do_sample", True)
    model = _FakeModel()

    local_generator(_FakeTokenizer(), model)("sys", "usr")

    assert model.kwargs["temperature"] == settings.generation_temperature
    assert model.kwargs["top_p"] == settings.generation_top_p
    assert model.kwargs["top_k"] == settings.generation_top_k


def test_the_two_backend_names_are_the_ones_the_contract_publishes():
    # These strings reach RetrievalRequest.model, the trace, and the frontend's
    # GenerationModel union. A rename here is a silent contract break.
    assert (LOCAL, GEMINI) == ("local", "gemini")


# --- the Gemini backend -----------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


def _ok(text="Gemini's answer.", prompt=120, completion=30, thoughts=0, finish="STOP"):
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}],
        "usageMetadata": {
            "promptTokenCount": prompt,
            "candidatesTokenCount": completion,
            "thoughtsTokenCount": thoughts,
        },
    }


class _Transport(list):
    """Every outbound call, in order, plus the queue of responses to hand back.

    A list subclass so assertions read as `len(posted)` and `posted[0]["headers"]` — the
    calls are the thing under test, and the queue is setup.
    """

    def __init__(self):
        super().__init__()
        self.queue = []


@pytest.fixture()
def posted(monkeypatch):
    """Captures every outbound call and returns queued responses. No network, ever."""
    calls = _Transport()

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        nxt = calls.queue.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    monkeypatch.setattr(generation.httpx, "post", fake_post)
    # The 503 path sleeps 2s before retrying. Nothing is learned by waiting for it.
    monkeypatch.setattr(generation.time, "sleep", lambda _s: None)
    return calls


def test_a_successful_call_returns_text_and_the_reported_token_counts(posted):
    posted.queue.append(_FakeResponse(200, _ok(prompt=120, completion=30)))

    reply, prompt_tokens, completion_tokens = gemini_generator("k", "gemini-3.6-flash")("s", "u")

    assert reply == "Gemini's answer."
    # REPORTED by the API, not counted locally — the local backend's counts come from tensor
    # widths and these come from usageMetadata. Same tuple, two different provenances.
    assert (prompt_tokens, completion_tokens) == (120, 30)


def test_the_api_key_travels_in_a_header_and_never_in_the_url(posted):
    """A key in a URL ends up in access logs, proxy logs and browser history. This is the
    kind of thing that is correct the day it is written and regresses during a refactor."""
    posted.queue.append(_FakeResponse(200, _ok()))

    gemini_generator("SECRET-KEY", "gemini-3.6-flash")("s", "u")

    assert posted[0]["headers"]["x-goog-api-key"] == "SECRET-KEY"
    assert "SECRET-KEY" not in posted[0]["url"]
    assert "key=" not in posted[0]["url"]


def test_the_model_name_is_configuration_and_goes_into_the_path(posted):
    """MEASURED BEHAVIOUR 3: model names expire. gemini-2.0-flash and gemini-2.5-flash both
    answer 404 'no longer available to new users'. The name is config, not a constant."""
    posted.queue.append(_FakeResponse(200, _ok()))

    gemini_generator("k", "gemini-9.9-future")("s", "u")

    assert "models/gemini-9.9-future:generateContent" in posted[0]["url"]


def test_text_is_joined_across_parts_rather_than_read_from_the_first(posted):
    """MEASURED BEHAVIOUR 4: a response carrying a thought signature splits the text across
    `content.parts`. Reading parts[0] silently truncates the answer to its first fragment."""
    posted.queue.append(_FakeResponse(200, {
        "candidates": [{"content": {"parts": [
            {"text": "The runway "}, {"text": "inspection is "}, {"text": "quarterly."},
        ]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 2},
    }))

    reply, _, _ = gemini_generator("k", "m")("s", "u")

    assert reply == "The runway inspection is quarterly."


def test_an_overload_is_retried_exactly_once_and_then_succeeds(posted):
    """MEASURED BEHAVIOUR 2: 'currently experiencing high demand' on a first call,
    succeeding seconds later. Retried once, like Spring retries this service."""
    posted.queue.extend([_FakeResponse(503), _FakeResponse(200, _ok(text="Second time lucky."))])

    reply, _, _ = gemini_generator("k", "m")("s", "u")

    assert reply == "Second time lucky."
    assert len(posted) == 2, "exactly one retry — a retry loop on a busy upstream is an attack on it"


def test_an_overload_that_persists_is_reported_as_temporary(posted):
    posted.queue.extend([_FakeResponse(503), _FakeResponse(503)])

    with pytest.raises(GeminiUnavailable) as failure:
        gemini_generator("k", "m")("s", "u")

    assert "overloaded" in str(failure.value)
    assert "try again" in str(failure.value).lower(), "an overload IS worth retrying"
    assert len(posted) == 2


def test_quota_exhaustion_does_not_tell_the_user_to_try_again(posted):
    """The distinction that cost a day of confusion. 429 is the free tier's
    GenerateRequestsPerDayPerProjectPerModel — per DAY, per MODEL. 'Try again in a moment'
    is FALSE ADVICE for a daily cap: waiting will not help, and the fix is a different model
    or the local backend. Two failures that look alike and need opposite words."""
    posted.queue.append(_FakeResponse(429))

    with pytest.raises(GeminiUnavailable) as failure:
        gemini_generator("k", "gemini-3.6-flash")("s", "u")

    message = str(failure.value)
    assert "daily free quota" in message
    assert "gemini-3.6-flash" in message, "the cap is per MODEL, so the message must name it"
    assert "per model" in message
    assert "try again" not in message.lower()
    assert len(posted) == 1, "a daily cap must not be retried"


def test_any_other_http_status_is_refused_without_echoing_the_body(posted):
    """The body can echo the prompt — i.e. the user's document text — back. Only the status
    reaches the message, which is the same rule tests/test_log_redaction.py enforces."""
    posted.queue.append(_FakeResponse(404, {"error": {"message": "model gemini-2.0-flash not found"}}))

    with pytest.raises(GeminiUnavailable) as failure:
        gemini_generator("k", "m")("s", "u")

    assert "HTTP 404" in str(failure.value)
    assert "gemini-2.0-flash" not in str(failure.value)


def test_a_transport_failure_is_unavailable_rather_than_a_crash(posted):
    """No network, DNS failure, timeout. A 503 'try again' for the caller, not a 500
    'this service is broken' — Spring turns the two into different things for the user."""
    posted.queue.append(httpx.ConnectError("no route to host"))

    with pytest.raises(GeminiUnavailable) as failure:
        gemini_generator("k", "m")("s", "u")

    assert "could not reach Gemini" in str(failure.value)
    assert "ConnectError" in str(failure.value), "the transport fault class is the diagnosis"


def test_a_budget_spent_entirely_on_thinking_is_an_error_not_an_empty_answer(posted):
    """MEASURED BEHAVIOUR 1, and the subtlest. Gemini 3.x reasons before writing and
    thoughtsTokenCount counts against maxOutputTokens, so a too-small cap is consumed
    entirely by thinking: finishReason MAX_TOKENS and `answer` an EMPTY STRING with no error
    anywhere. Returned as-is, that empty string reaches the grounding guard, scores 0.0 and
    is recorded as a model failure — when it is a budget misconfiguration."""
    posted.queue.append(_FakeResponse(200, _ok(text="", thoughts=500, finish="MAX_TOKENS")))

    with pytest.raises(GeminiUnavailable) as failure:
        gemini_generator("k", "m")("s", "u")

    assert "thinking" in str(failure.value)
    assert "500" in str(failure.value), "the thought count is the diagnosis and the fix"


def test_hitting_the_cap_with_text_already_written_is_kept(posted):
    """MAX_TOKENS alone is not the failure — a truncated answer is still an answer, and the
    parser salvages it. Only MAX_TOKENS *with nothing written* is the budget bug."""
    posted.queue.append(_FakeResponse(200, _ok(text="A partial ans", finish="MAX_TOKENS")))

    reply, _, _ = gemini_generator("k", "m")("s", "u")

    assert reply == "A partial ans"


def test_the_request_carries_the_configured_budget_and_thinking_limits(posted):
    posted.queue.append(_FakeResponse(200, _ok()))

    gemini_generator("k", "m")("s", "u")

    config = posted[0]["json"]["generationConfig"]
    assert config["maxOutputTokens"] == settings.gemini_max_output_tokens
    assert config["thinkingConfig"]["thinkingBudget"] == settings.gemini_thinking_budget
    assert posted[0]["timeout"] == settings.gemini_timeout_seconds
    # The system prompt must stay in systemInstruction rather than being folded into the
    # user turn, for the same untrusted-input reason as the local backend.
    assert posted[0]["json"]["systemInstruction"]["parts"][0]["text"] == "s"
    assert posted[0]["json"]["contents"][0]["parts"][0]["text"] == "u"


def test_a_missing_candidates_array_degrades_to_an_empty_reply_not_a_crash(posted):
    """A shape this service has not seen but cannot rule out. An IndexError here would be a
    500 from the product path; an empty reply is handled downstream by the grounding guard."""
    posted.queue.append(_FakeResponse(200, {"usageMetadata": {}}))

    reply, prompt_tokens, completion_tokens = gemini_generator("k", "m")("s", "u")

    assert reply == ""
    assert (prompt_tokens, completion_tokens) == (0, 0)
