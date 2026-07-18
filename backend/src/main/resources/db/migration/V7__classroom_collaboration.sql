ALTER TABLE classrooms ADD COLUMN IF NOT EXISTS join_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE classroom_members ADD COLUMN IF NOT EXISTS last_read_message_at TIMESTAMPTZ;

ALTER TABLE assignments ADD COLUMN IF NOT EXISTS share_kind VARCHAR(30) NOT NULL DEFAULT 'TEACHER_ASSIGNMENT';
ALTER TABLE assignments ADD COLUMN IF NOT EXISTS show_score BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE assignments ADD COLUMN IF NOT EXISTS allow_review BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE assignments ADD COLUMN IF NOT EXISTS shuffle_questions BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE assignments ADD COLUMN IF NOT EXISTS shuffle_options BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE assignments ADD COLUMN IF NOT EXISTS show_leaderboard BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE attempts ADD COLUMN IF NOT EXISTS show_score BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE attempts ADD COLUMN IF NOT EXISTS allow_review BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE assignments DROP CONSTRAINT IF EXISTS ck_assignments_share_kind;
ALTER TABLE assignments ADD CONSTRAINT ck_assignments_share_kind
    CHECK (share_kind IN ('TEACHER_ASSIGNMENT', 'MEMBER_SHARE'));

CREATE TABLE classroom_topic_shares (
    id UUID PRIMARY KEY,
    classroom_id UUID NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
    topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    shared_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX uq_classroom_topic_shares_active
    ON classroom_topic_shares(classroom_id, topic_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_classroom_topic_shares_topic ON classroom_topic_shares(topic_id, classroom_id);

CREATE TABLE classroom_messages (
    id UUID PRIMARY KEY,
    classroom_id UUID NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message_type VARCHAR(30) NOT NULL,
    content TEXT,
    topic_share_id UUID REFERENCES classroom_topic_shares(id) ON DELETE SET NULL,
    assignment_id UUID REFERENCES assignments(id) ON DELETE SET NULL,
    edited_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_classroom_message_type CHECK (message_type IN
        ('TEXT','IMAGE','FILE','TOPIC_SHARE','QUIZ_SHARE','SYSTEM')),
    CONSTRAINT ck_classroom_message_content CHECK
        (deleted_at IS NOT NULL OR content IS NOT NULL OR topic_share_id IS NOT NULL OR assignment_id IS NOT NULL
            OR message_type IN ('IMAGE', 'FILE'))
);
CREATE INDEX idx_classroom_messages_cursor
    ON classroom_messages(classroom_id, created_at DESC, id DESC);

CREATE TABLE classroom_attachments (
    id UUID PRIMARY KEY,
    classroom_id UUID NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
    uploader_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message_id UUID REFERENCES classroom_messages(id) ON DELETE CASCADE,
    object_key VARCHAR(1000) NOT NULL UNIQUE,
    original_name VARCHAR(255) NOT NULL,
    media_type VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL,
    image BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(20) NOT NULL DEFAULT 'READY',
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_classroom_attachment_status CHECK (status IN ('READY','ATTACHED','REJECTED')),
    CONSTRAINT ck_classroom_attachment_size CHECK (size_bytes > 0)
);
CREATE INDEX idx_classroom_attachments_pending
    ON classroom_attachments(expires_at) WHERE message_id IS NULL;
