ALTER TABLE attempts
    ADD COLUMN IF NOT EXISTS assignment_due_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS max_score NUMERIC(10, 2);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'attempts'
          AND column_name = 'total_questions'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'attempts'
              AND column_name = 'total_count'
        ) THEN
            ALTER TABLE attempts RENAME COLUMN total_count TO total_questions;
        ELSE
            ALTER TABLE attempts ADD COLUMN total_questions INTEGER;
        END IF;
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'attempts'
          AND column_name = 'total_count'
    ) THEN
        UPDATE attempts
        SET total_questions = COALESCE(total_questions, total_count);
        ALTER TABLE attempts DROP CONSTRAINT IF EXISTS ck_attempts_counts;
        ALTER TABLE attempts DROP COLUMN total_count;
    END IF;
END $$;

UPDATE attempts attempt
SET assignment_due_at = assignment.due_at
FROM assignments assignment
WHERE attempt.assignment_id = assignment.id
  AND attempt.assignment_due_at IS NULL;

UPDATE attempts attempt
SET total_questions = COALESCE(NULLIF(attempt.total_questions, 0), snapshot.total, 0)
FROM (
    SELECT attempt_id, COUNT(*)::INTEGER AS total
    FROM attempt_question_snapshots
    GROUP BY attempt_id
) snapshot
WHERE snapshot.attempt_id = attempt.id
  AND (attempt.total_questions IS NULL OR attempt.total_questions = 0);

UPDATE attempts
SET total_questions = 0
WHERE total_questions IS NULL;

UPDATE attempts attempt
SET max_score = snapshot.total_points
FROM (
    SELECT attempt_id, SUM(points)::NUMERIC(10, 2) AS total_points
    FROM attempt_question_snapshots
    GROUP BY attempt_id
) snapshot
WHERE snapshot.attempt_id = attempt.id
  AND attempt.max_score IS NULL;

UPDATE attempts
SET max_score = ROUND(score * 100 / percentage, 2)
WHERE max_score IS NULL
  AND score IS NOT NULL
  AND percentage IS NOT NULL
  AND percentage > 0;

UPDATE attempts attempt
SET deadline_at = CASE
    WHEN attempt.assignment_due_at IS NOT NULL
        THEN LEAST(attempt.started_at + make_interval(mins => quiz.duration_minutes), attempt.assignment_due_at)
    ELSE attempt.started_at + make_interval(mins => quiz.duration_minutes)
END
FROM quizzes quiz
WHERE quiz.id = attempt.quiz_id
  AND attempt.deadline_at IS NULL;

-- Defensive fallback for legacy rows. The quiz foreign key normally makes this update unnecessary.
UPDATE attempts
SET deadline_at = started_at
WHERE deadline_at IS NULL;

ALTER TABLE attempts
    ALTER COLUMN total_questions SET NOT NULL,
    ALTER COLUMN deadline_at SET NOT NULL;

ALTER TABLE attempts DROP CONSTRAINT IF EXISTS ck_attempts_counts;
ALTER TABLE attempts
    ADD CONSTRAINT ck_attempts_counts CHECK (
        (correct_count IS NULL OR correct_count >= 0)
        AND total_questions >= 0
        AND (correct_count IS NULL OR correct_count <= total_questions)
    );

ALTER TABLE attempts DROP CONSTRAINT IF EXISTS ck_attempts_max_score;
ALTER TABLE attempts
    ADD CONSTRAINT ck_attempts_max_score CHECK (max_score IS NULL OR max_score >= 0);
