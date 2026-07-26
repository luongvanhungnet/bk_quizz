ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS upstream_request_id VARCHAR(100);
