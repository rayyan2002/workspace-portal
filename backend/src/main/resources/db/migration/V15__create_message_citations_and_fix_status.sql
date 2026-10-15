-- V15__create_message_citations_and_fix_status.sql
--
-- Two corrections, both of the same kind: a column or table that described an
-- intention nobody had implemented.
--
-- 1. documents.status was set to 'pending' at upload and never touched again,
--    because the ingestion pipeline it describes (chunk -> embed -> index) is
--    Month-3 work. Every document therefore sat at 'pending' forever while being
--    perfectly readable and downloadable. Mark the stored ones 'ready', which is
--    what they actually are; 'processing' and 'failed' stay in the enum for the
--    real pipeline to start using.
UPDATE documents
SET status = 'ready'
WHERE status IN ('pending', 'uploading')
  AND storage_path IS NOT NULL;

-- 2. The citations table has existed since V7 and no code has ever read or written
--    it — the frontend renders citation cards, the schema holds citations, and
--    nothing connected the two. Adding created_at so citations can be ordered
--    stably, matching every other table.
ALTER TABLE citations ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX idx_citations_message ON citations(message_id);
