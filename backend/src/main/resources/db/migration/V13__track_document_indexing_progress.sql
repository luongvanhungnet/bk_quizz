ALTER TABLE source_documents
    ADD COLUMN IF NOT EXISTS indexing_progress_at TIMESTAMPTZ;

UPDATE source_documents
SET indexing_progress_at = COALESCE(indexed_at, processed_at, updated_at, created_at, NOW())
WHERE indexing_progress_at IS NULL;

ALTER TABLE source_documents
    ALTER COLUMN indexing_progress_at SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_source_documents_processing_delay
    ON source_documents(status, indexing_progress_at)
    WHERE deleted_at IS NULL;
