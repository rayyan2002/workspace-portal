-- Document chunks and their embeddings — the storage Month 3 retrieval reads from.
--
-- PREREQUISITE, AND IT IS NOT IN THIS FILE:
--     psql -d <database> -c "CREATE EXTENSION vector;"
--
-- Creating the extension needs superuser, and putting a superuser step inside a migration
-- would either fail for an ordinary application role or push a privileged credential into
-- the repository. It is a runbook step, documented in README.md. On a FRESH database this
-- migration fails without it — which is the intended, loud failure rather than a silent one.
--
-- On this machine the extension also could not come from `brew install pgvector`: that
-- bottle builds for postgresql@17 and @18, and this cluster is 16.14. It was built from
-- source with PG_CONFIG pointing at postgresql@16. See README.md.

CREATE TABLE document_chunks (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- ON DELETE CASCADE, deliberately unlike citations.document_id which is RESTRICT.
    -- A chunk is DERIVED data: delete it and it can be regenerated from the document, and
    -- embedding is bit-for-bit deterministic (Day 4), so regeneration is exact. A citation
    -- is a RECORD OF WHAT THE ASSISTANT SAID and must not vanish when a file is tidied up.
    -- Same column shape, opposite answer, for a reason that survives being asked about.
    document_id              UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,

    -- 1-based, document-wide. This is the number a citation resolves to.
    ordinal                  INT  NOT NULL,

    text                     TEXT NOT NULL,
    token_count              INT  NOT NULL,

    -- Offsets index into the EXTRACTED text, not the original file. For a PDF those differ
    -- entirely — do not use them to highlight the source document.
    char_start               INT  NOT NULL,
    char_end                 INT  NOT NULL,

    -- Markdown heading or spreadsheet sheet name; NULL when the format has no such notion.
    -- This is what finally replaces the literal string "Placeholder section" that
    -- CitationCard.tsx has been rendering since Month 2.
    section                  VARCHAR(255),

    -- 1-based, PDFs only.
    page                     INT,

    -- 384 = BAAI/bge-small-en-v1.5. Fixed here; changing it needs a new migration AND a
    -- re-embed of every row. Vectors are stored NORMALISED, so cosine similarity is the dot
    -- product and retrieval can use <#>. That is an obligation as much as an optimisation:
    -- a column mixing normalised and un-normalised rows ranks nonsensically and nothing
    -- would report an error.
    embedding                vector(384) NOT NULL,

    -- Which vector SPACE this row belongs to. Without it, re-embedding with a different
    -- model leaves two spaces in one column and similarity search silently returns nonsense.
    -- With it, rows from an older model are simply invisible to the current query.
    embedding_model          VARCHAR(255) NOT NULL,
    embedding_model_revision VARCHAR(64)  NOT NULL,

    created_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- Re-ingesting a document must not duplicate its chunks.
    CONSTRAINT uq_chunk_document_ordinal UNIQUE (document_id, ordinal),

    CONSTRAINT chk_chunk_ordinal  CHECK (ordinal >= 1),
    CONSTRAINT chk_chunk_span     CHECK (char_end >= char_start),
    CONSTRAINT chk_chunk_tokens   CHECK (token_count >= 1)
);

-- NOTE on a constraint deliberately NOT added: token_count <= 510.
-- 510 is bge's content ceiling (512 minus the [CLS]/[SEP] the encoder adds). It is a
-- property of the EMBEDDING MODEL, not of the schema, and embedding_model is already
-- recorded per row. A CHECK here would have to be migrated every time the model changed,
-- and migrations are forward-only. The ceiling is enforced where it belongs: in the chunker.

-- Retrieval filters by document before it ranks by distance: Spring passes the set of
-- documents the caller may see, and Python applies it unconditionally.
CREATE INDEX idx_chunks_document ON document_chunks (document_id);

-- Lets a re-embed find rows from a superseded model without scanning the table.
CREATE INDEX idx_chunks_model ON document_chunks (embedding_model, embedding_model_revision);

-- NO VECTOR INDEX YET, deliberately.
-- ivfflat builds clusters from the data it is given; with a corpus this small the clusters
-- are noise, and a sequential scan over a few hundred rows is likely to beat any index.
-- Adding one now would be cargo cult. Day 5's benchmark measures where the crossover
-- actually is, and an index arrives in its own migration when the number says so.

COMMENT ON TABLE  document_chunks IS 'Chunks of extracted document text with their embeddings. Derived data: regenerable from documents.';
COMMENT ON COLUMN document_chunks.char_start IS 'Offset into the EXTRACTED text, not the original file.';
COMMENT ON COLUMN document_chunks.embedding  IS 'Normalised vector(384) from bge-small-en-v1.5. Cosine similarity = dot product.';
