-- V18 stored these values as SMALLINT while the JPA model uses java.lang.Integer.
-- Rebuild the generated column after widening its input columns so Hibernate
-- schema validation is identical on Neon and local PostgreSQL.
ALTER TABLE questions
    DROP CONSTRAINT IF EXISTS ck_questions_cognitive_policy;

ALTER TABLE questions
    DROP COLUMN IF EXISTS complexity_score;

ALTER TABLE questions
    ALTER COLUMN concept_count TYPE INTEGER USING concept_count::INTEGER,
    ALTER COLUMN reasoning_step_count TYPE INTEGER USING reasoning_step_count::INTEGER;

ALTER TABLE questions
    ADD COLUMN complexity_score INTEGER
    GENERATED ALWAYS AS (
        concept_count + 2 * reasoning_step_count
        + CASE WHEN requires_novel_scenario THEN 1 ELSE 0 END
        + CASE WHEN requires_comparison THEN 1 ELSE 0 END
    ) STORED;

ALTER TABLE questions
    ADD CONSTRAINT ck_questions_cognitive_policy CHECK (
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
    ALTER COLUMN complexity_score TYPE INTEGER USING complexity_score::INTEGER;
