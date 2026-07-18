DO $migration$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'user_preferences'
          AND column_name = 'email_assignment_reminders'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'user_preferences'
          AND column_name = 'email_study_reminders'
    ) THEN
        ALTER TABLE user_preferences
            RENAME COLUMN email_assignment_reminders TO email_study_reminders;
    ELSIF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'user_preferences'
          AND column_name = 'email_study_reminders'
    ) THEN
        ALTER TABLE user_preferences
            ADD COLUMN email_study_reminders BOOLEAN NOT NULL DEFAULT TRUE;
    END IF;
END
$migration$;
