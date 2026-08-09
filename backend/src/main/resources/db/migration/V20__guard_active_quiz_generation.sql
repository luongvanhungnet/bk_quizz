CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_quiz_generation
    ON jobs(resource_id)
    WHERE type = 'QUIZ_GENERATION'
      AND status IN ('QUEUED', 'RUNNING', 'RETRY')
      AND resource_id IS NOT NULL;
