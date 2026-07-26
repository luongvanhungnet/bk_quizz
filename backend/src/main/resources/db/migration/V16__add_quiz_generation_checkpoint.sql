ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS checkpoint_payload JSONB;
