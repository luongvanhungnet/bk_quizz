CREATE TABLE job_events (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    occurred_at TIMESTAMPTZ NOT NULL,
    level VARCHAR(12) NOT NULL,
    code VARCHAR(80) NOT NULL,
    message VARCHAR(1000) NOT NULL,
    progress INTEGER,
    provider VARCHAR(40),
    batch_index INTEGER,
    part_index INTEGER,
    request_id VARCHAR(100),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_job_events_level
        CHECK (level IN ('INFO', 'WARNING', 'ERROR', 'SUCCESS')),
    CONSTRAINT ck_job_events_progress
        CHECK (progress IS NULL OR progress BETWEEN 0 AND 100)
);

CREATE INDEX idx_job_events_job_cursor ON job_events(job_id, id);

INSERT INTO job_events (
    job_id, occurred_at, level, code, message, progress, request_id, metadata
)
SELECT
    id,
    updated_at,
    CASE
        WHEN status = 'SUCCEEDED' THEN 'SUCCESS'
        WHEN status = 'FAILED' THEN 'ERROR'
        WHEN status = 'RETRY' THEN 'WARNING'
        ELSE 'INFO'
    END,
    COALESCE(NULLIF(current_step, ''), status),
    CASE
        WHEN status = 'SUCCEEDED' THEN 'Quiz đã được tạo thành công.'
        WHEN status = 'FAILED' THEN COALESCE(error_message, 'Tạo quiz thất bại.')
        WHEN status = 'RETRY' THEN 'Tác vụ đang chờ thử lại.'
        WHEN status = 'RUNNING' THEN 'Tác vụ đang được xử lý.'
        ELSE 'Tác vụ đang chờ bộ xử lý.'
    END,
    progress_percent,
    upstream_request_id,
    '{"backfilled":true}'::jsonb
FROM jobs
WHERE type = 'QUIZ_GENERATION';
