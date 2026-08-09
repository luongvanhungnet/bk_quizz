ALTER TABLE source_chunks
    ADD COLUMN IF NOT EXISTS snapshot_fingerprint VARCHAR(64),
    ADD COLUMN IF NOT EXISTS active_snapshot BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE source_chunks DROP CONSTRAINT IF EXISTS uq_source_chunks_document_index;
CREATE UNIQUE INDEX IF NOT EXISTS uq_source_chunks_active_document_index
    ON source_chunks (document_id, chunk_index)
    WHERE active_snapshot;
CREATE INDEX IF NOT EXISTS idx_source_chunks_document_active
    ON source_chunks (document_id, active_snapshot, chunk_index);

ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS validation_reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS validation_reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS validation_review_note VARCHAR(500);

ALTER TABLE quizzes DROP CONSTRAINT IF EXISTS ck_quizzes_ai_validation_status;
ALTER TABLE quizzes ADD CONSTRAINT ck_quizzes_ai_validation_status
    CHECK (ai_validation_status IN ('VERIFIED', 'WARNING', 'REVIEWED'));

ALTER TABLE questions DROP CONSTRAINT IF EXISTS ck_questions_ai_validation_status;
ALTER TABLE questions ADD CONSTRAINT ck_questions_ai_validation_status
    CHECK (ai_validation_status IN ('VERIFIED', 'WARNING', 'REVIEWED'));

ALTER TABLE attempt_question_snapshots
    DROP CONSTRAINT IF EXISTS ck_attempt_snapshots_ai_validation_status;
ALTER TABLE attempt_question_snapshots
    ADD CONSTRAINT ck_attempt_snapshots_ai_validation_status
    CHECK (ai_validation_status IN ('VERIFIED', 'WARNING', 'REVIEWED'));
