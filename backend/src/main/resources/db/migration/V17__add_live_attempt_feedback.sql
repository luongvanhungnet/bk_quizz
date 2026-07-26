ALTER TABLE attempts
    ADD COLUMN IF NOT EXISTS mode VARCHAR(30) NOT NULL DEFAULT 'STANDARD';

ALTER TABLE attempts DROP CONSTRAINT IF EXISTS ck_attempts_mode;
ALTER TABLE attempts
    ADD CONSTRAINT ck_attempts_mode
    CHECK (mode IN ('STANDARD', 'LIVE_FEEDBACK'));

ALTER TABLE attempt_answers
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;

ALTER TABLE attempt_answers DROP CONSTRAINT IF EXISTS ck_attempt_answers_confirmed_at;
ALTER TABLE attempt_answers
    ADD CONSTRAINT ck_attempt_answers_confirmed_at
    CHECK (
        confirmed_at IS NULL
        OR graded_at IS NOT NULL
    );

CREATE INDEX IF NOT EXISTS idx_attempt_answers_confirmed
    ON attempt_answers (attempt_id, confirmed_at)
    WHERE confirmed_at IS NOT NULL;
