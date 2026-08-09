ALTER TABLE quizzes
    ADD COLUMN IF NOT EXISTS cognitive_mode VARCHAR(20);

UPDATE quizzes
SET cognitive_mode = CASE difficulty
    WHEN 'EASY' THEN 'L1'
    WHEN 'MEDIUM' THEN 'L3'
    WHEN 'HARD' THEN 'L5'
    ELSE 'BALANCED'
END
WHERE cognitive_mode IS NULL;

ALTER TABLE quizzes ALTER COLUMN cognitive_mode SET NOT NULL;
ALTER TABLE quizzes DROP CONSTRAINT IF EXISTS ck_quizzes_cognitive_mode;
ALTER TABLE quizzes ADD CONSTRAINT ck_quizzes_cognitive_mode
    CHECK (cognitive_mode IN ('L1','L2','L3','L4','L5','BALANCED'));

ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS cognitive_level VARCHAR(10),
    ADD COLUMN IF NOT EXISTS concept_count SMALLINT,
    ADD COLUMN IF NOT EXISTS reasoning_step_count SMALLINT,
    ADD COLUMN IF NOT EXISTS requires_novel_scenario BOOLEAN,
    ADD COLUMN IF NOT EXISTS answer_directly_present BOOLEAN,
    ADD COLUMN IF NOT EXISTS requires_comparison BOOLEAN,
    ADD COLUMN IF NOT EXISTS complexity_verified BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cognitive_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE questions
SET cognitive_level = CASE difficulty
    WHEN 'EASY' THEN 'L1'
    WHEN 'HARD' THEN 'L5'
    ELSE 'L3'
END
WHERE cognitive_level IS NULL;

ALTER TABLE questions ALTER COLUMN cognitive_level SET NOT NULL;
ALTER TABLE questions DROP CONSTRAINT IF EXISTS ck_questions_cognitive_level;
ALTER TABLE questions ADD CONSTRAINT ck_questions_cognitive_level
    CHECK (cognitive_level IN ('L1','L2','L3','L4','L5'));
ALTER TABLE questions DROP CONSTRAINT IF EXISTS ck_questions_cognitive_counts;
ALTER TABLE questions ADD CONSTRAINT ck_questions_cognitive_counts CHECK (
    (complexity_verified = FALSE)
    OR (
        concept_count IS NOT NULL AND concept_count BETWEEN 1 AND 6
        AND reasoning_step_count IS NOT NULL AND reasoning_step_count BETWEEN 0 AND 5
        AND requires_novel_scenario IS NOT NULL
        AND answer_directly_present IS NOT NULL
        AND requires_comparison IS NOT NULL
    )
);

ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS complexity_score SMALLINT
    GENERATED ALWAYS AS (
        concept_count + 2 * reasoning_step_count
        + CASE WHEN requires_novel_scenario THEN 1 ELSE 0 END
        + CASE WHEN requires_comparison THEN 1 ELSE 0 END
    ) STORED;

ALTER TABLE questions DROP CONSTRAINT IF EXISTS ck_questions_cognitive_policy;
ALTER TABLE questions ADD CONSTRAINT ck_questions_cognitive_policy CHECK (
    complexity_verified = FALSE OR
    (cognitive_level = 'L1' AND concept_count = 1 AND reasoning_step_count = 0
        AND requires_novel_scenario = FALSE AND answer_directly_present = TRUE
        AND requires_comparison = FALSE AND complexity_score BETWEEN 1 AND 2) OR
    (cognitive_level = 'L2' AND concept_count BETWEEN 1 AND 2 AND reasoning_step_count = 1
        AND requires_novel_scenario = FALSE AND answer_directly_present = FALSE
        AND requires_comparison = FALSE AND complexity_score BETWEEN 3 AND 4) OR
    (cognitive_level = 'L3' AND concept_count BETWEEN 1 AND 2 AND reasoning_step_count BETWEEN 1 AND 2
        AND requires_novel_scenario = TRUE AND answer_directly_present = FALSE
        AND requires_comparison = FALSE AND complexity_score BETWEEN 5 AND 7) OR
    (cognitive_level = 'L4' AND concept_count BETWEEN 2 AND 4 AND reasoning_step_count BETWEEN 2 AND 3
        AND requires_novel_scenario = TRUE AND answer_directly_present = FALSE
        AND requires_comparison = TRUE AND complexity_score BETWEEN 8 AND 10) OR
    (cognitive_level = 'L5' AND concept_count BETWEEN 3 AND 6 AND reasoning_step_count BETWEEN 3 AND 5
        AND requires_novel_scenario = TRUE AND answer_directly_present = FALSE
        AND requires_comparison = TRUE AND complexity_score >= 11)
);

ALTER TABLE attempt_question_snapshots
    ADD COLUMN IF NOT EXISTS cognitive_level VARCHAR(10),
    ADD COLUMN IF NOT EXISTS complexity_score SMALLINT,
    ADD COLUMN IF NOT EXISTS complexity_verified BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cognitive_profile_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE attempt_question_snapshots snapshots
SET cognitive_level = questions.cognitive_level,
    complexity_score = questions.complexity_score,
    complexity_verified = questions.complexity_verified,
    cognitive_profile_snapshot = questions.cognitive_metadata
FROM questions
WHERE snapshots.source_question_id = questions.id
  AND snapshots.cognitive_level IS NULL;

UPDATE attempt_question_snapshots SET cognitive_level = 'L3' WHERE cognitive_level IS NULL;
ALTER TABLE attempt_question_snapshots ALTER COLUMN cognitive_level SET NOT NULL;
ALTER TABLE attempt_question_snapshots DROP CONSTRAINT IF EXISTS ck_attempt_snapshots_cognitive_level;
ALTER TABLE attempt_question_snapshots ADD CONSTRAINT ck_attempt_snapshots_cognitive_level
    CHECK (cognitive_level IN ('L1','L2','L3','L4','L5'));

CREATE INDEX IF NOT EXISTS idx_questions_quiz_cognitive_level
    ON questions (quiz_id, cognitive_level);
