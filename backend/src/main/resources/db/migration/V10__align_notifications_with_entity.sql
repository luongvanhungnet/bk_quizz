-- Align the legacy notification schema with the Notification entity. Classroom
-- join writes a notification in the same transaction, so these columns must be
-- usable before membership can be committed.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='related_resource_type')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='related_type') THEN
        ALTER TABLE notifications RENAME COLUMN related_resource_type TO related_type;
    ELSIF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='related_resource_type') THEN
        UPDATE notifications SET related_type = COALESCE(related_type, related_resource_type);
        ALTER TABLE notifications DROP COLUMN related_resource_type;
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='related_type') THEN
        ALTER TABLE notifications ADD COLUMN related_type VARCHAR(80);
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='related_resource_id')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='related_id') THEN
        ALTER TABLE notifications RENAME COLUMN related_resource_id TO related_id;
    ELSIF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='related_resource_id') THEN
        UPDATE notifications SET related_id = COALESCE(related_id, related_resource_id);
        ALTER TABLE notifications DROP COLUMN related_resource_id;
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='related_id') THEN
        ALTER TABLE notifications ADD COLUMN related_id UUID;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='dedup_key')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='deduplication_key') THEN
        ALTER TABLE notifications RENAME COLUMN dedup_key TO deduplication_key;
    ELSIF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='dedup_key') THEN
        UPDATE notifications SET deduplication_key = COALESCE(deduplication_key, dedup_key);
        ALTER TABLE notifications DROP COLUMN dedup_key;
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='deduplication_key') THEN
        ALTER TABLE notifications ADD COLUMN deduplication_key VARCHAR(200);
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='email_requested')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='email_required') THEN
        ALTER TABLE notifications RENAME COLUMN email_requested TO email_required;
    ELSIF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='email_requested') THEN
        UPDATE notifications SET email_required = email_required OR email_requested;
        ALTER TABLE notifications DROP COLUMN email_requested;
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='email_required') THEN
        ALTER TABLE notifications ADD COLUMN email_required BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;

ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0;

UPDATE notifications SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE notifications ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE notifications
    ALTER COLUMN related_type TYPE VARCHAR(80) USING LEFT(related_type, 80),
    ALTER COLUMN deduplication_key TYPE VARCHAR(200) USING LEFT(deduplication_key, 200);

DROP INDEX IF EXISTS uq_notifications_user_dedup;
CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_user_deduplication
    ON notifications (user_id, deduplication_key)
    WHERE deduplication_key IS NOT NULL;
