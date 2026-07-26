CREATE INDEX IF NOT EXISTS idx_jobs_document_queue
    ON jobs (priority, available_at, created_at)
    WHERE type IN ('SOURCE_INGESTION', 'RAG_INDEX_POLL')
      AND status IN ('QUEUED', 'RETRY');
