"""Chunks in, vector records out.

FOUR DECISIONS.

1. NORMALISE AT WRITE TIME, ALWAYS.
   With ||v|| == 1, cosine similarity IS the dot product. That makes the contract's `score`
   fall out of the arithmetic with no conversion, and it lets Day 5 use pgvector's inner
   product operator (`<#>`) instead of cosine distance (`<=>`) — same ranking, less work per
   comparison. The cost is that it must be done consistently: a mix of normalised and
   un-normalised rows in one column ranks nonsensically and nothing would report an error.

2. THE MODEL'S IDENTITY TRAVELS WITH EVERY VECTOR.
   `embedding_model` and `embedding_model_revision` are on each record so the chunk row
   records which vector SPACE it belongs to. Without it, re-embedding with a different model
   leaves two spaces in one column and similarity search silently returns nonsense. With it,
   old rows are simply invisible to the new query.

3. DIMENSION IS CHECKED PER BATCH, NOT ONLY AT STARTUP.
   The Flyway column is a fixed width. A vector of the wrong length can never be stored, so
   the useful place to fail is here, with a message naming both numbers — not at the database
   with a constraint violation.

4. "RETRY HANDLING" MEANS SOMETHING DIFFERENT FOR A LOCAL MODEL.
   The tracker lists retries under this day, which assumes an API: transient network faults,
   rate limits, 5xx. None of those exist here. A local encode either succeeds or fails
   DETERMINISTICALLY — retrying a bad input just fails again, slower.
   The one real transient failure is memory pressure on a large batch, and the correct
   response is not to retry the same batch but to HALVE it. That is implemented; blind
   retries are not, deliberately.
"""
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.config import settings
from app.ingestion.chunk import Chunk

log = logging.getLogger(__name__)

# Measured on the real corpus (177 chunks, lengths 2-510, median 478). Larger batches are
# 2-3x SLOWER here, in both sweep directions, so it is not thermal throttling:
#
#     batch    1     4     8    16    32    64
#     ms/chunk 88   142   180   236   227   286     (sweep 1 -> 64)
#     ms/chunk 91   133   143   184   236   256     (sweep 64 -> 1)
#
# WHY: PADDING, caused by MIXED CHUNK LENGTHS. Controlled test, same chunk count, two
# arrangements (benchmarks/10_batch_vs_heterogeneity.py):
#
#     homogeneous, all ~480 tokens   30,720 real tokens   batch64/batch1 = 0.89  (batching WINS)
#     mixed, half 480 half ~10       15,584 real tokens   batch64/batch1 = 3.72  (batching loses)
#
# The mixed set has HALF the real work and batch 64 took nearly twice as long on it. Short
# chunks are padded up to the longest member of their batch and cost the same as long ones.
#
# sentence-transformers does length-sort before batching, which is why this was not obvious.
# But sorting only helps when batches are SMALLER than the length spread: at batch_size >=
# len(texts) there is exactly one batch and everything pads to its longest member.
#
# So 1 is right for THIS corpus because it is length-heterogeneous (spreadsheet rows and CSV
# rows pack to ~500, while short markdown files are a handful of tokens). A corpus of
# uniform-length chunks would prefer a larger batch — hence batch_size stays configurable.
#
# TWO EARLIER EXPLANATIONS HERE WERE WRONG and are recorded rather than quietly deleted:
# "one long sequence already saturates six cores" (contradicted by
# benchmarks/07_batch_vs_threads.py: at 6 threads with 220-token chunks, batch 16 won), and
# "sequence length decides it" (contradicted by 06, where uniform 510-token chunks gave
# ratios of 1.03, 1.67, 1.19 and 0.90 — noise straddling neutral). The decision never moved;
# only the story did.
DEFAULT_BATCH_SIZE = 1
MIN_BATCH_SIZE = 1

EncodeFn = Callable[[Sequence[str], int], Sequence[Sequence[float]]]
"""(texts, batch_size) -> one vector per text. Injected so tests never load a model."""


class EmbeddingError(Exception):
    """Embedding failed in a way the caller cannot fix by trying again."""


@dataclass(frozen=True)
class EmbeddedChunk:
    """Exactly what IngestResponse.Chunk declares, plus the vector and its provenance."""

    ordinal: int
    text: str
    token_count: int
    char_start: int
    char_end: int
    section: str | None
    page: int | None
    embedding: list[float]
    embedding_model: str
    embedding_model_revision: str


class Embedder:
    def __init__(
        self,
        encode: EncodeFn,
        dim: int,
        model: str,
        revision: str,
        batch_size: int = DEFAULT_BATCH_SIZE,
        query_prefix: str = settings.query_prefix,
    ) -> None:
        self._encode = encode
        self._dim = dim
        self._model = model
        self._revision = revision
        self._batch_size = batch_size
        self._query_prefix = query_prefix

    def embed_query(self, question: str) -> list[float]:
        """The ONLY place the bge query prefix is applied.

        bge is trained asymmetrically: queries carry "Represent this sentence for
        searching relevant passages: " and documents carry nothing. Applying it to
        documents too would cancel the asymmetry; applying it in two places would
        guarantee the copies disagree. So it lives in config and is used here, once.
        `embed_chunks` deliberately does NOT touch it.

        MEASURED, and the honest version: on this corpus the prefix produced NO visible
        benefit — answerable/unanswerable separation was 0.177 with it and 0.172 without,
        which is noise at n=4. It stays because the model card specifies it and because a
        2.72x-duplicated corpus of seeded stubs is not something to re-derive a model's
        training convention from. Revisit with the Day 13 golden set, not before.
        """
        vectors = self._encode_all([self._query_prefix + question])
        return list(vectors[0])

    def embed_chunks(self, chunks: Sequence[Chunk]) -> list[EmbeddedChunk]:
        if not chunks:
            return []

        vectors = self._encode_all([c.text for c in chunks])
        if len(vectors) != len(chunks):
            raise EmbeddingError(f"got {len(vectors)} vectors for {len(chunks)} chunks")

        return [
            EmbeddedChunk(
                ordinal=c.ordinal,
                text=c.text,
                token_count=c.token_count,
                char_start=c.char_start,
                char_end=c.char_end,
                section=c.section,
                page=c.page,
                embedding=list(v),
                embedding_model=self._model,
                embedding_model_revision=self._revision,
            )
            for c, v in zip(chunks, vectors, strict=True)
        ]

    # -- internals -----------------------------------------------------------

    def _encode_all(self, texts: list[str]) -> list[Sequence[float]]:
        vectors = self._encode_with_backoff(texts, self._batch_size)
        for i, v in enumerate(vectors):
            if len(v) != self._dim:
                # Fail here, naming both numbers, rather than at a Postgres constraint.
                raise EmbeddingError(
                    f"chunk {i} embedded to {len(v)} dimensions, "
                    f"but the schema is built for {self._dim}"
                )
        return vectors

    def _encode_with_backoff(self, texts: list[str], batch_size: int) -> list[Sequence[float]]:
        """Halve the batch on memory pressure. NOT a retry loop.

        Retrying the same batch after MemoryError repeats a deterministic failure. Halving
        changes the thing that failed, which is the only version of "retry" that means
        anything for local inference.
        """
        try:
            return list(self._encode(texts, batch_size))
        except MemoryError:
            if batch_size <= MIN_BATCH_SIZE:
                raise EmbeddingError(
                    f"out of memory embedding a single chunk of {len(texts[0])} characters"
                ) from None
            halved = max(MIN_BATCH_SIZE, batch_size // 2)
            log.warning("embedding ran out of memory at batch %d, halving to %d", batch_size, halved)
            return self._encode_with_backoff(texts, halved)
