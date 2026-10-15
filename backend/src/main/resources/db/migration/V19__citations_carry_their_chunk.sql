-- Month 3 Day 9 — a citation can be traced back to the passage it came from.
--
-- Until now `citations` stored {message_id, document_id, section, excerpt}. The GenAI
-- service returns a chunk_id, Spring used it to look up the excerpt, and then dropped it.
-- Nothing could re-derive which passage was cited: not the page, not the retrieval score,
-- not the surrounding text. Day 18's observability work needs exactly that, and "which
-- chunk did the assistant actually use?" was unanswerable after the fact.

ALTER TABLE citations
    -- ON DELETE SET NULL, deliberately, and it is the third different rule on this table.
    --
    --   document_chunks -> documents   CASCADE   chunks are derived and regenerable
    --   citations       -> documents   RESTRICT  a citation must not outlive its document
    --   citations       -> chunks      SET NULL  <- this one
    --
    -- A chunk IS regenerable: embedding is bit-for-bit deterministic, so re-ingesting a
    -- document produces new chunk rows with new ids. CASCADE would then delete the
    -- citation — destroying a record of what the assistant said because an implementation
    -- detail was rebuilt. RESTRICT would block re-ingestion entirely. SET NULL keeps the
    -- citation, with its stored excerpt intact, and admits the link is gone.
    ADD COLUMN chunk_id UUID REFERENCES document_chunks (id) ON DELETE SET NULL,

    -- Denormalised from the chunk at write time rather than joined at read time, for the
    -- same reason `excerpt` already is: the chunk may be regenerated or deleted, and a
    -- citation is a record of what was true WHEN THE ASSISTANT SAID IT.
    ADD COLUMN page INT,

    -- Retrieval similarity, not answer confidence. Stored so a poor answer can be
    -- diagnosed later ("was this cited at 0.61 or 0.75?") and so the UI label has one
    -- source rather than being recomputed from nothing.
    ADD COLUMN score REAL;

COMMENT ON COLUMN citations.chunk_id IS
    'The passage cited. NULL once the chunk has been regenerated; the excerpt survives.';
COMMENT ON COLUMN citations.score IS
    'Cosine similarity of the chunk to the question. Retrieval confidence, NOT answer confidence.';

CREATE INDEX idx_citations_chunk ON citations (chunk_id);
