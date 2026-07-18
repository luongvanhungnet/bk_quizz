-- Preserve existing generation errors while aligning the legacy V1 column names
-- with the Quiz entity. The guards also support databases repaired manually.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'quizzes'
          AND column_name = 'generation_error_code'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'quizzes'
          AND column_name = 'error_code'
    ) THEN
        ALTER TABLE quizzes RENAME COLUMN generation_error_code TO error_code;
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'quizzes'
          AND column_name = 'generation_error_code'
    ) THEN
        UPDATE quizzes SET error_code = COALESCE(error_code, generation_error_code);
        ALTER TABLE quizzes DROP COLUMN generation_error_code;
    ELSIF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'quizzes'
          AND column_name = 'error_code'
    ) THEN
        ALTER TABLE quizzes ADD COLUMN error_code VARCHAR(80);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'quizzes'
          AND column_name = 'generation_error_message'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'quizzes'
          AND column_name = 'error_message'
    ) THEN
        ALTER TABLE quizzes RENAME COLUMN generation_error_message TO error_message;
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'quizzes'
          AND column_name = 'generation_error_message'
    ) THEN
        UPDATE quizzes SET error_message = COALESCE(error_message, generation_error_message);
        ALTER TABLE quizzes DROP COLUMN generation_error_message;
    ELSIF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'quizzes'
          AND column_name = 'error_message'
    ) THEN
        ALTER TABLE quizzes ADD COLUMN error_message VARCHAR(1000);
    END IF;
END $$;

ALTER TABLE quizzes
    ALTER COLUMN error_code TYPE VARCHAR(80) USING LEFT(error_code, 80),
    ALTER COLUMN error_message TYPE VARCHAR(1000) USING LEFT(error_message, 1000);

-- AI quizzes start at QUEUED, which was absent from the legacy V1 constraint.
ALTER TABLE quizzes DROP CONSTRAINT IF EXISTS ck_quizzes_status;
ALTER TABLE quizzes ADD CONSTRAINT ck_quizzes_status CHECK (
    status IN ('DRAFT', 'QUEUED', 'GENERATING', 'READY', 'PUBLISHED', 'ARCHIVED', 'FAILED')
);
