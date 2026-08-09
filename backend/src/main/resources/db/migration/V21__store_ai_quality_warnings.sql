ALTER TABLE quizzes
    ADD COLUMN IF NOT EXISTS ai_validation_status VARCHAR(12) NOT NULL DEFAULT 'VERIFIED',
    ADD COLUMN IF NOT EXISTS ai_validation_warnings JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS ai_validation_status VARCHAR(12) NOT NULL DEFAULT 'VERIFIED',
    ADD COLUMN IF NOT EXISTS validation_warnings JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE attempt_question_snapshots
    ADD COLUMN IF NOT EXISTS ai_validation_status VARCHAR(12) NOT NULL DEFAULT 'VERIFIED',
    ADD COLUMN IF NOT EXISTS validation_warnings_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE quizzes DROP CONSTRAINT IF EXISTS ck_quizzes_ai_validation_status;
ALTER TABLE quizzes ADD CONSTRAINT ck_quizzes_ai_validation_status
    CHECK (ai_validation_status IN ('VERIFIED', 'WARNING'));

ALTER TABLE questions DROP CONSTRAINT IF EXISTS ck_questions_ai_validation_status;
ALTER TABLE questions ADD CONSTRAINT ck_questions_ai_validation_status
    CHECK (ai_validation_status IN ('VERIFIED', 'WARNING'));

ALTER TABLE attempt_question_snapshots
    DROP CONSTRAINT IF EXISTS ck_attempt_snapshots_ai_validation_status;
ALTER TABLE attempt_question_snapshots
    ADD CONSTRAINT ck_attempt_snapshots_ai_validation_status
    CHECK (ai_validation_status IN ('VERIFIED', 'WARNING'));
