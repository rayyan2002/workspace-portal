-- V13__add_document_ownership_and_storage.sql
--
-- Closes the last Day-16 gap. Documents were the one resource with no ownership at
-- all: every user saw every file. The download endpoint was deliberately deferred
-- rather than shipped with an ownership check it could not express, because the
-- column it needed did not exist. This adds it.
--
-- Also adds the physical-file columns. Until now the bytes were written to
-- uploads/<uuid> and that location was never recorded, so nothing could serve the
-- file back — the metadata knew a document existed but not where it lived.

ALTER TABLE documents ADD COLUMN owner_id     UUID;
ALTER TABLE documents ADD COLUMN storage_path VARCHAR(512);
ALTER TABLE documents ADD COLUMN content_type VARCHAR(255);

-- Backfill. The four seeded documents are SPLIT between the two users rather than
-- all assigned to one: with everything on user A, B's library would be empty and the
-- boundary would be invisible in the browser. Split, both users have a library and
-- the difference between the two windows is the demonstration.
--
-- One constraint on the split: the seeded citation (V8) links user A's assistant
-- message to document ...2224, so that document must belong to A or A's own chat
-- would cite a file A is not allowed to open.

-- User A
UPDATE documents SET owner_id = '11111111-1111-1111-1111-111111111111'
WHERE id IN (
    '22222222-2222-2222-2222-222222222221',  -- maintenance_log_Q2.md
    '22222222-2222-2222-2222-222222222224'   -- quarterly_financial_report.pdf (cited by A's message)
);

-- User B
UPDATE documents SET owner_id = '99999999-9999-9999-9999-999999999999'
WHERE id IN (
    '22222222-2222-2222-2222-222222222222',  -- FastAPI_Proxy_Architecture.md
    '22222222-2222-2222-2222-222222222223'   -- aerotwin_telemetry_spec_v2.pdf
);

-- Any document created before this migration that somehow escaped the split falls to
-- the primary seeded user, so the NOT NULL below cannot fail on unexpected rows.
UPDATE documents SET owner_id = '11111111-1111-1111-1111-111111111111' WHERE owner_id IS NULL;

-- Seeded documents have metadata but no bytes on disk. Recording the path they WOULD
-- occupy lets a dev-profile initializer materialise placeholder files, so "open the
-- original" is demonstrable without uploading something first.
UPDATE documents SET storage_path = 'uploads/' || id WHERE storage_path IS NULL;

UPDATE documents SET content_type = 'text/markdown'   WHERE filename LIKE '%.md'  AND content_type IS NULL;
UPDATE documents SET content_type = 'application/pdf' WHERE filename LIKE '%.pdf' AND content_type IS NULL;
UPDATE documents SET content_type = 'application/octet-stream' WHERE content_type IS NULL;

-- Now that every row has an owner, make it structural. Ownership that is merely
-- usually-set is not ownership; an orphan document would be invisible to everyone
-- and permanently unreachable.
ALTER TABLE documents ALTER COLUMN owner_id SET NOT NULL;
ALTER TABLE documents ADD CONSTRAINT fk_documents_owner
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX idx_documents_owner ON documents(owner_id);
