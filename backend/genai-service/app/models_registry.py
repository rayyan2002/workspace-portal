"""Model loading and honest readiness reporting.

Loading happens once, at startup, in a background thread — deliberately not inline in
the lifespan hook. If loading blocked startup, the process would not accept connections
until both models were in memory, and during those ~45 seconds /health/live would be
connection-refused: indistinguishable from a crashed service. A liveness probe that
cannot tell "starting" from "dead" is what produces a restart loop under load.

So: the socket opens immediately, /health/live answers at once, and /health/ready
answers 503 MODEL_NOT_READY until both models have genuinely finished loading. Readiness
is set from the completed load, never from a flag set before it started.
"""
import logging
import threading
import time

from app.config import settings
from app.schemas import ModelState

log = logging.getLogger(__name__)


class ModelRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.embedding_state = ModelState.LOADING
        self.generation_state = ModelState.LOADING
        self.embedding_error: str | None = None
        self.generation_error: str | None = None
        self.intent_error: str | None = None
        self.embedder = None
        self.tokenizer = None
        self.generator = None
        self.intent_router = None
        self.loading_started = False

    @property
    def is_ready(self) -> bool:
        return self.embedding_state is ModelState.READY and self.generation_state is ModelState.READY

    def status_message(self) -> str:
        if not self.loading_started:
            # Honest readiness means never reporting "loading" for something that was
            # never started. Otherwise a misconfigured service looks like a slow one.
            return "model loading was never started (GENAI_LOAD_MODELS=false)"
        if self.embedding_state is ModelState.FAILED:
            return f"embedding model failed to load: {self.embedding_error}"
        if self.generation_state is ModelState.FAILED:
            return f"generation model failed to load: {self.generation_error}"
        pending = [n for n, s in (("embedding", self.embedding_state), ("generation", self.generation_state))
                   if s is ModelState.LOADING]
        return f"{' and '.join(pending)} model loading"

    # -- loading ------------------------------------------------------------

    def start_loading(self) -> threading.Thread:
        self.loading_started = True
        thread = threading.Thread(target=self._load_all, name="model-loader", daemon=True)
        thread.start()
        return thread

    def _fail_remaining(self, reason: str) -> None:
        """Mark anything still LOADING as FAILED.

        The guarantee this buys: when the loader thread stops running, for ANY reason,
        nothing is left claiming to be in progress.
        """
        with self._lock:
            if self.embedding_state is ModelState.LOADING:
                self.embedding_state = ModelState.FAILED
                self.embedding_error = reason
            if self.generation_state is ModelState.LOADING:
                self.generation_state = ModelState.FAILED
                self.generation_error = reason

    def _load_all(self) -> None:
        """Everything the thread does is inside try/finally, including the imports.

        It was not, and that was a bug: `import torch` and set_num_threads sat outside
        both try blocks, so if either raised, the thread died with both states still
        LOADING and readiness answered "embedding and generation model loading" forever.
        A dead loader reported as a slow one — exactly what this class exists to prevent.
        Not hypothetical: the first install on this machine produced a numpy/torch ABI
        mismatch where `import torch` was the thing that raised.

        The `finally` is the mechanism rather than the memory: it catches an early
        `return` added later, just as it catches an exception today.
        """
        try:
            import torch

            if settings.torch_threads:
                torch.set_num_threads(settings.torch_threads)
            log.info("loading models on %d torch threads", torch.get_num_threads())

            self._load_embedding()
            # After the embedder and BEFORE the generator, because it needs the encoder and
            # the generator takes ~40s. Routing is usable the moment retrieval is.
            self._fit_intent_router()
            self._load_generation()
        except BaseException as exc:  # noqa: BLE001 — a dead thread must still be reportable
            log.exception("model loader thread died before finishing")
            self._fail_remaining(f"loader thread died: {exc}")
        finally:
            self._fail_remaining("loader thread exited without finishing the load")

    def _load_embedding(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer

            t0 = time.perf_counter()
            model = SentenceTransformer(
                settings.embedding_model,
                revision=settings.embedding_model_revision,
                device="cpu",
            )
            dim = model.get_sentence_embedding_dimension()
            if dim != settings.embedding_dim:
                # The vector column's width is fixed in the Flyway migration. A model whose
                # dimension disagrees with it can never produce a storable row, so fail at
                # startup rather than at the first ingestion.
                raise ValueError(
                    f"{settings.embedding_model} has dimension {dim}, "
                    f"but the schema is built for {settings.embedding_dim}"
                )
            with self._lock:
                self.embedder = model
                self.embedding_state = ModelState.READY
            log.info("embedding model ready in %.1fs (dim=%d)", time.perf_counter() - t0, dim)
        except Exception as exc:  # noqa: BLE001 — readiness must report the reason
            with self._lock:
                self.embedding_state = ModelState.FAILED
                self.embedding_error = str(exc)
            log.exception("embedding model failed to load")

    def _fit_intent_router(self) -> None:
        """Fits the tool-routing classifier from the committed training set. ~1.1s measured.

        DELIBERATELY NOT PART OF READINESS. /health/ready speaks for the two MODELS; a
        failure here must not take the service down, because routing degrades to the
        keyword rules and those have measured zero false positives on create-task. The
        service would lose the two tools keywords cannot express and keep answering
        questions, which is the right trade — the product is a knowledge assistant that
        also proposes actions, not an action router that also answers.

        Fitted rather than loaded from a pickle on purpose: the coefficients only mean
        anything in the vector space of the encoder actually in memory, and a committed
        model file is a second artefact that can disagree with it silently.
        """
        import numpy as np

        from app.intent import IntentRouter

        try:
            model = self.embedder
            if model is None:
                raise RuntimeError("no embedder; the embedding model did not load")
            router = IntentRouter.fit(
                # batch_size=32, not ingestion's 1. The 1 is right for CHUNKS, which are
                # length-heterogeneous and pay for padding (see ingestion/embed.py); these
                # are 84 uniformly short sentences, where batching genuinely wins.
                lambda texts: np.asarray(model.encode(
                    list(texts), batch_size=32, normalize_embeddings=True,
                    show_progress_bar=False))
            )
            with self._lock:
                self.intent_router = router
        except Exception as exc:  # noqa: BLE001 — must never prevent the service answering
            log.exception("intent classifier failed to fit; routing falls back to keywords")
            self.intent_error = str(exc)

    def _load_generation(self) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            t0 = time.perf_counter()
            tokenizer = AutoTokenizer.from_pretrained(
                settings.generation_model, revision=settings.generation_model_revision
            )
            model = AutoModelForCausalLM.from_pretrained(
                settings.generation_model,
                revision=settings.generation_model_revision,
                torch_dtype=torch.float32,  # this machine is Intel CPU: no bf16, no MPS
            )
            model.eval()

            if not settings.generation_do_sample:
                # SILENCE THREE WARNINGS PER REQUEST, and the silence is the lesser point.
                #
                # Qwen ships generation_config.json with do_sample=True, temperature=0.7,
                # top_p=0.8 and top_k=20. Decoding here is GREEDY — a citation decision, not
                # a style one, because qa-v2 resolves citations by matching the model's quote
                # back to chunk text and sampling turns a resolvable quote into a dropped
                # one. So every request passed do_sample=False against a config that still
                # carried sampling parameters, and transformers warned three times:
                #
                #     `do_sample` is set to `False`. However, `temperature` is set to `0.7`
                #
                # Correct, repeated on every answer, and therefore trained into the
                # background. A log that cries wolf on every request is a log nobody reads
                # when it finally says something — which is the failure Day 17 found in a
                # different guise, and the reason Day 18 exists.
                #
                # Clearing them on the loaded config makes the model's own defaults agree
                # with how it is actually called. Nothing about the output changes: these
                # values were already unused.
                model.generation_config.do_sample = False
                model.generation_config.temperature = None
                model.generation_config.top_p = None
                model.generation_config.top_k = None
            with self._lock:
                self.tokenizer = tokenizer
                self.generator = model
                self.generation_state = ModelState.READY
            log.info("generation model ready in %.1fs", time.perf_counter() - t0)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self.generation_state = ModelState.FAILED
                self.generation_error = str(exc)
            log.exception("generation model failed to load")


registry = ModelRegistry()
