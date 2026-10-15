CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL,
    upload_date TIMESTAMPTZ NOT NULL DEFAULT now(),
    status VARCHAR(50) NOT NULL CHECK (status IN ('pending', 'uploading', 'processing', 'ready', 'failed'))
);