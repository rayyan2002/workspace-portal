import logging
import time
from uuid import UUID

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.config import settings
from app.ingestion import Embedder, UnsupportedDocument, chunk_document, extract
from app.ingestion.embed import DEFAULT_BATCH_SIZE
from app.models_registry import registry
from app.schemas import Chunk, ErrorCode, ErrorResponse, IngestResponse, IngestTrace, ModelState
from app.trace import current_trace_id
from app.verbose import print_chunking

log = logging.getLogger(__name__)
router = APIRouter(tags=["ingest"])

_ERRORS: dict[int | str, dict] = {
    415: {"model": ErrorResponse, "description": "The file type cannot be extracted"},
    422: {"model": ErrorResponse, "description": "The file contained no extractable text"},
    503: {"model": ErrorResponse, "description": "Embedding model not loaded"},
}


@router.post(
    "/ingest",
    response_model=IngestResponse,
    responses=_ERRORS,
    summary="Bytes in, chunks and vectors out. Writes nothing",
)
def ingest(
    file: UploadFile = File(
        ..., description="Document bytes. Spring sends them; Python never reads a filesystem"
    ),
    document_id: UUID = Form(..., description="Correlation only — Python does not look it up"),
    filename: str = Form(...),
    content_type: str = Form(...),
) -> IngestResponse:
    """Deliberately a plain `def`, not `async def`.

    Extraction and embedding are CPU-bound. Inside an `async def` they would block the
    event loop and take /health/live down with them — the FastAPI trap that has no Spring
    equivalent, where a slow call only ties up its own thread. A plain `def` endpoint runs
    in the threadpool.

    Spring writes every chunk row in one transaction and only then sets the document
    `ready`. A partially written document must never become retrievable.

    **IMPLEMENTED ON DAY 16, AND THIS IS THE DAY THE PRODUCT PATH FIRST RAN.** Every
    searchable document in the database before today was populated by
    `benchmarks/11_load_fixture_chunks.py`, whose own docstring says it "DELIBERATELY BREAKS
    RULE R1" and exists so Day 6 had data to measure retrieval against. The product's
    ingestion path did not exist; an uploaded document stored its bytes, went to
    `processing`, and stayed there. Day 11c built this and it was reverted; the only part
    kept was `page` and `section` on the Chunk contract, which is why they are already here.

    **NOTHING IS WRITTEN HERE AND THAT IS THE WHOLE BOUNDARY.** This service holds SELECT on
    the chunk tables. It returns rows; Spring inserts them, in one transaction, and owns the
    status transition. Rule R1 survives the one day it would have been most tempting to bend
    — a `psycopg` INSERT here would be ten lines shorter and would put schema ownership in
    two places.

    **The document_id is correlation only.** It is never looked up, because looking it up
    would mean this service deciding whether a document exists, which is Spring's to know.
    It appears in the response so Spring can match a reply to a request, and in the log line
    so a slow ingestion is traceable.
    """
    started = time.perf_counter()
    model = _embedding_model()
    embedder = _embedder(model)
    data = file.file.read()

    if not data:
        # An empty upload is not an extraction failure; there is nothing to extract from.
        # 422 rather than 415: the TYPE was fine, the content was not.
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.MALFORMED_REQUEST,
                     "The uploaded file was empty.")

    t0 = time.perf_counter()
    try:
        document = extract(data, filename)
    except UnsupportedDocument as unsupported:
        # 415, and it names the type. Spring's allow-list already rejects unknown extensions
        # at upload, so reaching here means the two allow-lists disagree — which is worth a
        # specific status rather than a generic failure.
        log.warning("ingest.unsupported documentId=%s contentType=%s", document_id, content_type)
        raise _error(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, ErrorCode.MALFORMED_REQUEST,
                     str(unsupported)) from None
    extract_ms = int((time.perf_counter() - t0) * 1000)

    if document.is_empty:
        # A scanned PDF with no text layer reaches here: valid file, zero characters. Saying
        # so is the difference between a document that FAILED and one that silently became
        # searchable with nothing in it — the second is the confident-wrong-signal failure
        # this project keeps finding, and it would look exactly like a working upload.
        log.warning("ingest.no_text documentId=%s kind=%s", document_id, document.kind)
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.MALFORMED_REQUEST,
                     "No readable text could be extracted. A scanned PDF needs OCR, which "
                     "this service does not do.")

    t1 = time.perf_counter()
    chunks = chunk_document(
        document,
        # THE EMBEDDING MODEL'S OWN TOKENIZER, and `add_special_tokens=False` is
        # load-bearing. max_chunk_tokens counts CONTENT tokens; bge adds [CLS] and [SEP] on
        # top. Counting with the special tokens included would make every chunk read as two
        # tokens longer and shrink them for no reason — counting without them while
        # budgeting 512 would overflow and truncate silently, which is the failure this
        # ceiling exists to prevent.
        count_tokens=lambda text: len(model.tokenizer.encode(text, add_special_tokens=False)),
        # 510, not 512: bge adds [CLS] and [SEP], so 512 content tokens arrive as 514 and
        # are SILENTLY truncated. Proven — a 1,145-token text and its 510-token prefix embed
        # to cosine 1.000000.
        max_tokens=settings.max_chunk_tokens,
        # SEMANTIC CHUNKING, when configured. The same encoder that will embed the chunks
        # also decides where they end — which is the point: boundaries are drawn in the
        # space the search actually happens in, not in punctuation.
        #
        # normalize_embeddings is left OFF and the chunker normalises instead. It compares
        # vectors and must not depend on a caller remembering to; an un-normalised vector
        # would still produce plausible-looking distances that mean nothing.
        embed_sentences=(
            None if settings.chunking_strategy == "sentence"
            # DEFAULT_BATCH_SIZE, the same constant embed.py uses — measured on this
            # corpus in benchmarks/05 and 10, not guessed.
            else lambda texts: model.encode(texts, batch_size=DEFAULT_BATCH_SIZE,
                                            show_progress_bar=False)
        ),
        breakpoint_percentile=settings.semantic_breakpoint_percentile,
        window_sentences=settings.semantic_window_sentences,
        min_distance=settings.semantic_min_distance,
        min_sentences=settings.semantic_min_sentences,
    )
    chunk_ms = int((time.perf_counter() - t1) * 1000)

    if not chunks:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.MALFORMED_REQUEST,
                     "The file produced no chunks.")

    t2 = time.perf_counter()
    embedded = embedder.embed_chunks(chunks)
    embed_ms = int((time.perf_counter() - t2) * 1000)

    total_ms = int((time.perf_counter() - started) * 1000)
    # APPENDED, not rewritten: every field this line already carried is still here and in
    # the same order, so anything parsing it keeps working. The chunking fields go on the
    # end — which strategy ran, and the size spread it produced.
    sizes = sorted(c.token_count for c in chunks)
    log.info(
        "ingest.done documentId=%s kind=%s chunks=%d extract=%dms chunk=%dms embed=%dms "
        "total=%dms strategy=%s median_tokens=%d min_tokens=%d max_tokens=%d segments=%d",
        document_id, document.kind, len(chunks), extract_ms, chunk_ms, embed_ms, total_ms,
        settings.chunking_strategy, sizes[len(sizes) // 2] if sizes else 0,
        sizes[0] if sizes else 0, sizes[-1] if sizes else 0, len(document.segments),
    )

    if settings.verbose_trace:
        print_chunking(
            document, chunks, settings.chunking_strategy,
            {} if settings.chunking_strategy == "sentence" else {
                "percentile": settings.semantic_breakpoint_percentile,
                "window": settings.semantic_window_sentences,
                "min_dist": settings.semantic_min_distance,
                "min_sent": settings.semantic_min_sentences,
            },
            chunk_ms,
            settings.max_chunk_tokens,
        )

    return IngestResponse(
        document_id=document_id,
        chunk_count=len(embedded),
        embedding_model=settings.embedding_model,
        embedding_model_revision=settings.embedding_model_revision,
        embedding_dim=settings.embedding_dim,
        chunking_strategy=settings.chunking_strategy,
        chunks=[
            Chunk(
                ordinal=c.ordinal,
                text=c.text,
                token_count=c.token_count,
                char_start=c.char_start,
                char_end=c.char_end,
                section=c.section,
                page=c.page,
                embedding=list(c.embedding),
            )
            for c in embedded
        ],
        trace=IngestTrace(
            trace_id=current_trace_id(),
            extract_ms=extract_ms,
            chunk_ms=chunk_ms,
            embed_ms=embed_ms,
            total_ms=total_ms,
        ),
    )


def _error(status_code: int, code: ErrorCode, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code.value, "message": message, "trace_id": current_trace_id()},
    )


def _embedding_model():
    """The loaded SentenceTransformer, or 503. Checked BEFORE the file is read.

    Ordering matters: reading and extracting a 40MB PDF and only then discovering the model
    is still loading wastes the work and delays the 503 the caller needs in order to retry.

    The handle is read once and tested, not inferred from the state flag — the two are set
    under the same lock and read without it, so testing the flag alone leaves a window where
    READY is visible before `embedder` is.
    """
    model = registry.embedder
    if registry.embedding_state is not ModelState.READY or model is None:
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, ErrorCode.MODEL_NOT_READY,
                     registry.status_message())
    return model


def _embedder(model) -> Embedder:
    """Wraps the loaded model. Cheap: it wraps, never loads."""
    return Embedder(
        encode=lambda texts, bs: np.asarray(
            model.encode(
                list(texts), batch_size=bs, normalize_embeddings=True, show_progress_bar=False
            )
        ).tolist(),
        dim=settings.embedding_dim,
        model=settings.embedding_model,
        revision=settings.embedding_model_revision,
    )
