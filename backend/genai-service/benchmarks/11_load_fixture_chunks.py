"""Load the real corpus into document_chunks so retrieval can be measured.  (~1 minute)

THIS SCRIPT DELIBERATELY BREAKS RULE R1. The integration contract says Python writes
nothing — Spring owns every write, and in production Spring will write these rows from what
POST /ingest returns. This is a BENCHMARK FIXTURE LOADER, not the ingestion path: Day 6
needs data in the table to measure retrieval against, and Spring's write path does not exist
until Day 8. It is named and placed so nobody mistakes it for the real thing.

Idempotent: deletes this document's chunks before inserting, so re-running does not
accumulate. Safe because chunks are derived data — the UNIQUE (document_id, ordinal) and
ON DELETE CASCADE in V18 both assume exactly this.
"""
import subprocess
import time
from pathlib import Path

import numpy as np
import psycopg
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

from app.config import settings
from app.ingestion import Embedder, UnsupportedDocument, chunk_document, extract

DSN = "dbname=knowledge_assistant"
UP = Path(__file__).resolve().parents[2] / "uploads"

tok = AutoTokenizer.from_pretrained(settings.embedding_model, revision=settings.embedding_model_revision)
model = SentenceTransformer(settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")
def encode(texts, batch_size):
    """np.asarray narrows the union.

    SentenceTransformer.encode() is declared as returning Tensor | ndarray | list[Tensor]
    depending on its flags, and `convert_to_numpy=True` does not narrow it for a type
    checker — this version has no overloads keyed on that argument. So `.tolist()` on the
    raw result was a type error the whole time, even though it worked at runtime.
    """
    vectors = model.encode(list(texts), batch_size=batch_size, normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=False)
    return np.asarray(vectors).tolist()


embedder = Embedder(
    encode=encode,
    dim=settings.embedding_dim,
    model=settings.embedding_model,
    revision=settings.embedding_model_revision,
)


def count(text: str) -> int:
    return len(tok.encode(text, add_special_tokens=False))


rows = subprocess.run(
    ["psql", "-d", "knowledge_assistant", "-At", "-F|", "-c",
     "SELECT id, filename FROM documents ORDER BY size_bytes DESC;"],
    capture_output=True, text=True).stdout.strip().splitlines()

t_start = time.perf_counter()
total = skipped = 0
with psycopg.connect(DSN) as conn:
    for line in rows:
        doc_id, name = line.split("|", 1)
        path = UP / doc_id
        if not path.exists():
            skipped += 1
            continue
        try:
            doc = extract(path.read_bytes(), name)
        except UnsupportedDocument as exc:
            print(f"  {name[:40]:<42} REJECTED: {exc}")
            skipped += 1
            continue
        if doc.is_empty:
            print(f"  {name[:40]:<42} EMPTY -> would be DocumentStatus.failed")
            skipped += 1
            continue

        chunks = chunk_document(doc, count, max_tokens=settings.max_chunk_tokens)
        embedded = embedder.embed_chunks(chunks)

        with conn.cursor() as cur:
            cur.execute("DELETE FROM document_chunks WHERE document_id = %s", (doc_id,))
            cur.executemany(
                """INSERT INTO document_chunks
                   (document_id, ordinal, text, token_count, char_start, char_end,
                    section, page, embedding, embedding_model, embedding_model_revision)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [(doc_id, e.ordinal, e.text, e.token_count, e.char_start, e.char_end,
                  e.section, e.page, str(e.embedding), e.embedding_model, e.embedding_model_revision)
                 for e in embedded])
        conn.commit()
        total += len(embedded)
        print(f"  {name[:40]:<42} {len(embedded):>3} chunks")

print(f"\n  {total} chunks written in {time.perf_counter() - t_start:.0f}s | {skipped} documents skipped")

with psycopg.connect(DSN) as conn, conn.cursor() as cur:
    # fetchone() is Row | None. These queries are aggregates so a row always comes back,
    # but the checker cannot know that and an unguarded [0] would be a real crash if the
    # query ever changed shape.
    cur.execute("SELECT count(*), count(DISTINCT document_id) FROM document_chunks")
    counts = cur.fetchone()
    assert counts is not None
    print(f"  table now holds {counts[0]} chunks across {counts[1]} documents")

    cur.execute("SELECT count(*) FROM document_chunks WHERE abs(1 - (embedding <#> embedding) * -1) > 1e-5")
    bad = cur.fetchone()
    assert bad is not None
    print(f"  rows whose stored vector is NOT unit norm: {bad[0]}")
    cur.execute("SELECT section, page, left(text, 48) FROM document_chunks WHERE section IS NOT NULL LIMIT 3")
    print("\n  sample metadata that will replace 'Placeholder section':")
    for section, page, text in cur.fetchall():
        print(f"    section={section!r:28} page={page}  {text!r}")
