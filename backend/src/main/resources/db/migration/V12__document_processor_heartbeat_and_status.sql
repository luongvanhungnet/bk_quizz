CREATE TABLE IF NOT EXISTS job_worker_heartbeats (
    worker_id VARCHAR(160) PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_job_worker_heartbeats_last_seen
    ON job_worker_heartbeats (last_seen_at DESC);

UPDATE source_documents source
SET status = 'UPLOADED',
    indexing_progress = 0,
    indexing_step = 'QUEUED'
WHERE source.status = 'EXTRACTING'
  AND source.rag_document_id IS NULL
  AND EXISTS (
      SELECT 1
      FROM jobs job
      WHERE job.resource_id = source.id
        AND job.type = 'SOURCE_INGESTION'
        AND job.status IN ('QUEUED', 'RETRY')
        AND job.attempts = 0
  );
