ALTER TABLE chat_threads DROP CONSTRAINT IF EXISTS ck_chat_threads_status;
ALTER TABLE chat_threads ADD CONSTRAINT ck_chat_threads_status
    CHECK (status IN ('ACTIVE', 'ARCHIVED', 'DELETED'));

CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_threads_active_attempt
    ON chat_threads (user_id, attempt_id)
    WHERE attempt_id IS NOT NULL AND status = 'ACTIVE' AND deleted_at IS NULL;

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS question_snapshot_id UUID,
    ADD COLUMN IF NOT EXISTS client_message_id UUID,
    ADD COLUMN IF NOT EXISTS reply_to_message_id UUID;

ALTER TABLE chat_messages
    ADD CONSTRAINT fk_chat_messages_question_snapshot
        FOREIGN KEY (question_snapshot_id) REFERENCES attempt_question_snapshots(id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_chat_messages_reply_to
        FOREIGN KEY (reply_to_message_id) REFERENCES chat_messages(id) ON DELETE SET NULL;

ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS ck_chat_messages_status;
ALTER TABLE chat_messages ADD CONSTRAINT ck_chat_messages_status
    CHECK (status IN ('PENDING', 'GENERATING', 'COMPLETED', 'FAILED', 'CANCELLED'));

ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS ck_chat_messages_completed_at;
ALTER TABLE chat_messages ADD CONSTRAINT ck_chat_messages_completed_at
    CHECK (
        (status IN ('COMPLETED', 'FAILED', 'CANCELLED') AND completed_at IS NOT NULL)
        OR status IN ('PENDING', 'GENERATING')
    );

ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS ck_chat_messages_content;
ALTER TABLE chat_messages ADD CONSTRAINT ck_chat_messages_content
    CHECK (
        status IN ('PENDING', 'GENERATING', 'FAILED', 'CANCELLED')
        OR btrim(content) <> ''
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_messages_client_id
    ON chat_messages (thread_id, client_message_id)
    WHERE client_message_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_messages_one_generating
    ON chat_messages (thread_id)
    WHERE role = 'ASSISTANT' AND status IN ('PENDING', 'GENERATING');

CREATE INDEX IF NOT EXISTS idx_chat_messages_question_snapshot
    ON chat_messages (question_snapshot_id, created_at);

ALTER TABLE chat_citations
    ADD COLUMN IF NOT EXISTS citation_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE chat_citations DROP CONSTRAINT IF EXISTS fk_chat_citations_chunk;
ALTER TABLE chat_citations ALTER COLUMN source_chunk_id DROP NOT NULL;
ALTER TABLE chat_citations ADD CONSTRAINT fk_chat_citations_chunk
    FOREIGN KEY (source_chunk_id) REFERENCES source_chunks(id) ON DELETE SET NULL;

ALTER TABLE chat_citations DROP CONSTRAINT IF EXISTS ck_chat_citations_metadata;
ALTER TABLE chat_citations ADD CONSTRAINT ck_chat_citations_metadata
    CHECK (jsonb_typeof(metadata) = 'object' AND jsonb_typeof(citation_snapshot) = 'object');
