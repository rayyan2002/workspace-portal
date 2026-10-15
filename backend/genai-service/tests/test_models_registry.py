"""Day 15: failure simulation for model loading. No weights are ever loaded here.

`app/models_registry.py` was 51% covered, and the uncovered half was ENTIRELY the failure
paths — which is the half that exists only for failures. A loader that reports honestly when
it dies is the whole reason this class is not three lines of `SentenceTransformer(...)` at
import time.

THE PROPERTY UNDER TEST, stated once: **readiness must never report "loading" for something
that is not loading.** A liveness probe that cannot tell "starting" from "dead" produces a
restart loop under load, and a human reading "still loading" does not investigate. This is
the project's recurring failure mode — a confident wrong signal — in the one place that
reports on itself.

`sentence_transformers` and `transformers` are injected through `sys.modules` rather than
imported, because the real imports live INSIDE the methods. That is deliberate in the
production code (a failing import must be catchable) and it is what makes this testable.
"""
import sys
import types

import pytest

from app.models_registry import ModelRegistry
from app.schemas import ModelState

# --- fakes ------------------------------------------------------------------

class _FakeEncoder:
    def __init__(self, dim=384):
        self._dim = dim

    def get_sentence_embedding_dimension(self):
        return self._dim

    def encode(self, texts, **_kwargs):
        import numpy as np

        # Unit-normalised rows, like the real encoder with normalize_embeddings=True.
        rows = np.ones((len(list(texts)), self._dim), dtype="float32")
        return rows / np.linalg.norm(rows, axis=1, keepdims=True)


@pytest.fixture()
def fake_sentence_transformers(monkeypatch):
    """Injects a `sentence_transformers` module whose SentenceTransformer we control."""
    captured = {}

    def install(dim=384, raises=None):
        def SentenceTransformer(name, revision=None, device=None):  # noqa: N802 — mirrors the real name
            captured.update(name=name, revision=revision, device=device)
            if raises is not None:
                raise raises
            return _FakeEncoder(dim)

        module = types.ModuleType("sentence_transformers")
        # Through __dict__: a stub module has no declared attributes, so direct assignment
        # is a type error and setattr with a literal name is a lint error. Writing the
        # module's namespace is what both of those were approximating anyway.
        module.__dict__["SentenceTransformer"] = SentenceTransformer
        monkeypatch.setitem(sys.modules, "sentence_transformers", module)
        return captured

    return install


# --- honest readiness reporting ---------------------------------------------

def test_a_registry_that_never_started_says_so_rather_than_loading():
    """GENAI_LOAD_MODELS=false is a normal configuration — the whole test suite runs under
    it. Reporting "loading" for something nobody started makes a misconfigured service look
    like a slow one."""
    registry = ModelRegistry()

    assert registry.loading_started is False
    assert "never started" in registry.status_message()
    assert "GENAI_LOAD_MODELS" in registry.status_message(), "name the switch that caused it"
    assert registry.is_ready is False


def test_a_failed_embedding_model_is_named_with_its_reason():
    registry = ModelRegistry()
    registry.loading_started = True
    registry.embedding_state = ModelState.FAILED
    registry.embedding_error = "dimension 768 does not fit a 384 column"

    assert "embedding model failed" in registry.status_message()
    assert "768" in registry.status_message(), "the reason is the actionable part"


def test_a_failed_generation_model_is_reported_even_when_embedding_is_fine():
    registry = ModelRegistry()
    registry.loading_started = True
    registry.embedding_state = ModelState.READY
    registry.generation_state = ModelState.FAILED
    registry.generation_error = "no such revision"

    assert "generation model failed" in registry.status_message()
    assert registry.is_ready is False, "one failed model is not readiness"


def test_a_partially_loaded_registry_names_only_what_is_still_pending():
    registry = ModelRegistry()
    registry.loading_started = True
    registry.embedding_state = ModelState.READY

    message = registry.status_message()

    assert "generation" in message
    assert "embedding" not in message, "a model that finished must not be reported as pending"


def test_readiness_needs_both_models():
    registry = ModelRegistry()
    registry.embedding_state = ModelState.READY
    assert registry.is_ready is False

    registry.generation_state = ModelState.READY
    assert registry.is_ready is True


# --- the embedding model ----------------------------------------------------

def test_the_embedding_model_is_pinned_by_revision_not_just_by_name(fake_sentence_transformers):
    """A model name is mutable upstream; a revision is not. Every vector in the database
    records the revision it came from, so loading a different one silently creates a second
    vector space in one column — which ranks nonsensically with no error anywhere."""
    captured = fake_sentence_transformers(dim=384)
    registry = ModelRegistry()

    registry._load_embedding()

    assert registry.embedding_state is ModelState.READY
    assert captured["revision"], "loaded without a revision pin"
    assert captured["device"] == "cpu", "this machine is an Intel Mac: no MPS, no CUDA"


def test_a_dimension_mismatch_fails_at_startup_rather_than_at_first_ingestion(fake_sentence_transformers):
    """The vector column's width is fixed by a Flyway migration. A model whose dimension
    disagrees can NEVER produce a storable row, so the useful place to fail is here — with a
    message naming BOTH numbers — rather than at the first upload with a constraint
    violation from Postgres."""
    fake_sentence_transformers(dim=768)
    registry = ModelRegistry()

    registry._load_embedding()

    assert registry.embedding_state is ModelState.FAILED
    assert "768" in (registry.embedding_error or "")
    assert "384" in (registry.embedding_error or ""), "both numbers, or the reader cannot act on it"
    assert registry.embedder is None, "a rejected model must not be left usable"


def test_an_embedding_model_that_cannot_load_at_all_is_reported_not_raised(fake_sentence_transformers):
    """Raising here would kill the loader thread with the generation model still LOADING.
    The state must carry the reason instead, because /health/ready is the only thing that
    can tell an operator what happened."""
    fake_sentence_transformers(raises=OSError("no such revision"))
    registry = ModelRegistry()

    registry._load_embedding()

    assert registry.embedding_state is ModelState.FAILED
    assert "no such revision" in (registry.embedding_error or "")


# --- the generation model ---------------------------------------------------

def test_a_generation_model_that_cannot_load_is_reported_not_raised(monkeypatch):
    module = types.ModuleType("transformers")

    def _boom(*_a, **_k):
        raise OSError("gated repo")

    module.__dict__["AutoTokenizer"] = types.SimpleNamespace(from_pretrained=_boom)
    module.__dict__["AutoModelForCausalLM"] = types.SimpleNamespace(from_pretrained=_boom)
    monkeypatch.setitem(sys.modules, "transformers", module)
    registry = ModelRegistry()

    registry._load_generation()

    assert registry.generation_state is ModelState.FAILED
    assert "gated repo" in (registry.generation_error or "")
    assert registry.generator is None and registry.tokenizer is None


# --- the loader thread as a whole -------------------------------------------

def test_nothing_is_left_claiming_to_be_in_progress_when_the_thread_exits(monkeypatch):
    """The `finally` in _load_all is the mechanism rather than the memory: it catches an
    early `return` added later just as it catches an exception today. A loader that returns
    without finishing must not leave a state saying LOADING forever."""
    registry = ModelRegistry()
    monkeypatch.setattr(registry, "_load_embedding", lambda: None)   # returns, sets nothing
    monkeypatch.setattr(registry, "_fit_intent_router", lambda: None)
    monkeypatch.setattr(registry, "_load_generation", lambda: None)

    registry.start_loading().join(timeout=10)

    assert registry.embedding_state is ModelState.FAILED
    assert registry.generation_state is ModelState.FAILED
    assert "without finishing" in registry.status_message()


def test_a_successful_load_is_not_overwritten_by_the_final_sweep(monkeypatch):
    """The other half of the same guarantee: _fail_remaining must touch ONLY what is still
    LOADING. If it clobbered READY states the service could never become ready at all."""
    registry = ModelRegistry()

    def ready_embedding():
        registry.embedding_state = ModelState.READY

    def ready_generation():
        registry.generation_state = ModelState.READY

    monkeypatch.setattr(registry, "_load_embedding", ready_embedding)
    monkeypatch.setattr(registry, "_fit_intent_router", lambda: None)
    monkeypatch.setattr(registry, "_load_generation", ready_generation)

    registry.start_loading().join(timeout=10)

    assert registry.is_ready is True


# --- the intent classifier, which is deliberately NOT part of readiness ------

def test_a_classifier_that_cannot_fit_does_not_take_the_service_down(monkeypatch):
    """DELIBERATE, and the trade-off is worth stating. /health/ready speaks for the two
    MODELS. Routing degrades to the keyword rules, which have measured zero false positives
    on create-task; the service loses the two tools keywords cannot express and keeps
    answering questions. The product is a knowledge assistant that also proposes actions,
    not an action router that also answers."""
    registry = ModelRegistry()
    registry.embedder = None   # no embedder -> the fit cannot proceed

    registry._fit_intent_router()

    assert registry.intent_router is None
    assert registry.intent_error is not None, "a silent degradation is one nobody can audit"
    # The states it must NOT have touched:
    assert registry.embedding_state is ModelState.LOADING
    assert registry.generation_state is ModelState.LOADING


def test_the_classifier_is_fitted_from_the_committed_training_set(fake_sentence_transformers):
    """Fitted rather than loaded from a pickle: the coefficients only mean anything in the
    vector space of the encoder actually in memory, and a committed model file is a second
    artefact that can disagree with it silently."""
    fake_sentence_transformers(dim=384)
    registry = ModelRegistry()
    registry._load_embedding()

    registry._fit_intent_router()

    assert registry.intent_router is not None
    assert registry.intent_router.classifier_ready is True
    assert registry.intent_error is None


def test_the_classifier_is_fitted_before_the_slow_generation_model(monkeypatch):
    """Ordering, asserted because it is easy to lose in a refactor and silent when lost.
    The generation model takes ~40s; routing only needs the encoder, so it becomes usable
    the moment retrieval does rather than 40 seconds later."""
    order = []
    registry = ModelRegistry()
    monkeypatch.setattr(registry, "_load_embedding", lambda: order.append("embedding"))
    monkeypatch.setattr(registry, "_fit_intent_router", lambda: order.append("intent"))
    monkeypatch.setattr(registry, "_load_generation", lambda: order.append("generation"))

    registry.start_loading().join(timeout=10)

    assert order == ["embedding", "intent", "generation"]
