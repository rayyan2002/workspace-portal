"""Day 4 tests.

No model is loaded: the encoder is injected, exactly as the tokenizer is in the chunker.
These test the contract around embedding — dimension, provenance, batching behaviour — not
whether bge produces good vectors, which is Day 13's question.
"""
import pytest

from app.ingestion import Chunk, EmbeddedChunk, Embedder, EmbeddingError

DIM = 384


def chunk(ordinal: int = 1, text: str = "some text", section: str | None = "S", page: int | None = 2):
    return Chunk(ordinal=ordinal, text=text, token_count=2, char_start=0,
                 char_end=len(text), section=section, page=page)


def encoder(dim: int = DIM, record: list | None = None):
    def encode(texts, batch_size):
        if record is not None:
            record.append((len(texts), batch_size))
        return [[0.1] * dim for _ in texts]
    return encode


def test_every_chunk_field_survives_embedding():
    """The vector is added; nothing the chunker worked out is lost on the way through."""
    source = chunk(ordinal=7, text="Final approval rests with the line manager.", section="Approval", page=4)
    out = Embedder(encoder(), DIM, "bge", "rev1").embed_chunks([source])[0]
    assert isinstance(out, EmbeddedChunk)
    assert (out.ordinal, out.section, out.page) == (7, "Approval", 4)
    assert (out.char_start, out.char_end) == (source.char_start, source.char_end)
    assert out.text == source.text and out.token_count == source.token_count


def test_model_identity_is_recorded_on_every_vector():
    """Without it, re-embedding with another model leaves two vector spaces in one column
    and similarity search returns nonsense with no error anywhere."""
    out = Embedder(encoder(), DIM, "BAAI/bge-small-en-v1.5", "5c38ec7").embed_chunks([chunk()])[0]
    assert out.embedding_model == "BAAI/bge-small-en-v1.5"
    assert out.embedding_model_revision == "5c38ec7"


def test_a_wrong_dimension_fails_here_naming_both_numbers():
    """The Flyway column is a fixed width, so such a vector can never be stored. Failing at
    the database would surface as a constraint violation that names neither number."""
    with pytest.raises(EmbeddingError) as e:
        Embedder(encoder(dim=768), DIM, "bge", "rev1").embed_chunks([chunk()])
    assert "768" in str(e.value) and "384" in str(e.value)


def test_no_chunks_means_no_model_call():
    calls: list = []
    assert Embedder(encoder(record=calls), DIM, "bge", "rev1").embed_chunks([]) == []
    assert calls == []


def test_the_configured_batch_size_reaches_the_encoder():
    calls: list = []
    Embedder(encoder(record=calls), DIM, "bge", "rev1", batch_size=8).embed_chunks(
        [chunk(i) for i in range(1, 21)])
    assert calls == [(20, 8)]


def test_memory_pressure_halves_the_batch_instead_of_retrying_it():
    """Retrying the same batch after MemoryError repeats a deterministic failure. Halving
    changes the thing that failed — the only version of 'retry' that means anything for
    local inference, where there is no network and no rate limit."""
    attempts: list[int] = []

    def flaky(texts, batch_size):
        attempts.append(batch_size)
        if batch_size > 4:
            raise MemoryError("simulated pressure")
        return [[0.1] * DIM for _ in texts]

    out = Embedder(flaky, DIM, "bge", "rev1", batch_size=16).embed_chunks([chunk(i) for i in range(1, 6)])
    assert attempts == [16, 8, 4]
    assert len(out) == 5


def test_memory_pressure_on_a_single_chunk_gives_up_with_a_clear_reason():
    def always_oom(texts, batch_size):
        raise MemoryError("nope")

    with pytest.raises(EmbeddingError, match="single chunk"):
        Embedder(always_oom, DIM, "bge", "rev1", batch_size=2).embed_chunks([chunk()])


def test_a_short_vector_count_is_caught_rather_than_silently_zipped():
    def drops_one(texts, batch_size):
        return [[0.1] * DIM for _ in texts][:-1]

    with pytest.raises(EmbeddingError, match="vectors"):
        Embedder(drops_one, DIM, "bge", "rev1").embed_chunks([chunk(1), chunk(2)])


def test_the_default_batch_size_is_the_measured_one():
    """1, not 16 or 32.

    Measured twice on the real corpus, once in each direction, to rule out thermal
    throttling: batch 1 is ~2x faster than batch 64 here regardless of run order. A further
    sweep at uniform lengths showed WHY — batching helps below ~120 tokens and stops helping
    by ~360, and this corpus has a median of 478.

    This asserts the default has not drifted back to a conventional value that is slower on
    this data. It is a property of the corpus and the hardware, not of the model: a corpus
    of short prose chunks would want a larger batch, which is why batch_size is a parameter.
    """
    from app.ingestion.embed import DEFAULT_BATCH_SIZE

    assert DEFAULT_BATCH_SIZE == 1
