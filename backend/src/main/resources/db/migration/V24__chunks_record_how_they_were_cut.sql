-- Which chunking strategy produced each row.
--
-- WHY. The chunker gained a second strategy: "sentence" packs whole sentences up to the
-- token ceiling, "semantic" embeds every sentence and cuts where neighbouring meaning
-- diverges most. Changing the setting does NOT re-chunk what is already stored, so a corpus
-- is mixed the moment it changes — and this table had no way to say which row was which.
--
-- It was answerable only by INFERENCE, from the size profile:
--
--     Suzuki_Swift_2026_Pakistan_Guide.pdf   11 chunks   median 184   max 400   -> semantic
--     Junior_Fullstack_GenAI_Training.xlsx   19 chunks   median 480   max 509   -> sentence
--
-- Reading a strategy out of a histogram is exactly the kind of knowledge that lives in one
-- person's head and leaves with them.
--
-- THE PRECEDENT IS IN THIS TABLE ALREADY. V18 added embedding_model for the same reason and
-- said so: "Without it, re-embedding with a different model leaves two spaces in one column
-- and similarity search silently returns nonsense." Chunking is the gentler version of that
-- failure — mixed chunk shapes still search correctly, they just answer with different
-- amounts of context, and nothing in the system could tell you that was happening.
--
-- NULLABLE, and no backfill. Rows ingested before this migration were cut by the sentence
-- packer, and writing "sentence" into them would be an inference presented as a record. The
-- size profile above is evidence; a column is a claim. NULL honestly means "not recorded".

ALTER TABLE document_chunks ADD COLUMN chunking_strategy VARCHAR(20);

-- The same two values app/config.py accepts. Constrained for the reason decision and status
-- are constrained on action_audit: a typo in a Python literal should fail on write, not
-- surface weeks later as a strategy nothing has a branch for.
ALTER TABLE document_chunks
    ADD CONSTRAINT chk_chunk_strategy
    CHECK (chunking_strategy IS NULL OR chunking_strategy IN ('sentence', 'semantic'));

-- Lets "show me everything still cut the old way" be an index scan rather than a scan of
-- every chunk in the corpus, which is what a re-chunking sweep needs to find its work.
CREATE INDEX idx_chunks_strategy ON document_chunks (chunking_strategy);

COMMENT ON COLUMN document_chunks.chunking_strategy IS
    'How this chunk was cut: sentence (pack whole sentences to the ceiling) or semantic (cut where meaning diverges). NULL for rows ingested before V24, which were all sentence-packed.';
