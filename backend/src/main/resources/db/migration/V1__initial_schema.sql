-- BKQuiz initial PostgreSQL schema.
-- Target: PostgreSQL 16. This migration contains the schema currently mapped by
-- the application. Vector persistence will be introduced by a later migration
-- together with the SourceChunk embedding mapping; keeping it out of V1 allows
-- the current backend to run on both PostgreSQL and the pgvector image.



CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- =========================================================
-- Common trigger
-- =========================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

-- =========================================================
-- 1. Identity, users and administration
-- =========================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) NOT NULL,
    email CITEXT NOT NULL,
    password_hash VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'STUDENT',
    avatar_url TEXT,
    bio TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    email_verified_at TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    deletion_requested_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT ck_users_role
        CHECK (role IN ('STUDENT', 'TEACHER', 'ADMIN')),
    CONSTRAINT ck_users_failed_login_count
        CHECK (failed_login_count >= 0),
    CONSTRAINT ck_users_username_length
        CHECK (char_length(username) BETWEEN 3 AND 50)
);

CREATE INDEX idx_users_role_active
    ON users (role, active)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_users_email_trgm
    ON users USING gin ((email::text) gin_trgm_ops);

CREATE INDEX idx_users_username_trgm
    ON users USING gin (username gin_trgm_ops);

CREATE TABLE user_preferences (
    user_id UUID PRIMARY KEY,
    email_assignment_reminders BOOLEAN NOT NULL DEFAULT TRUE,
    email_deadline_reminders BOOLEAN NOT NULL DEFAULT TRUE,
    email_product_updates BOOLEAN NOT NULL DEFAULT FALSE,
    public_profile BOOLEAN NOT NULL DEFAULT FALSE,
    attempt_autosave BOOLEAN NOT NULL DEFAULT TRUE,
    deadline_reminder_hours INTEGER NOT NULL DEFAULT 24,
    locale VARCHAR(20) NOT NULL DEFAULT 'vi-VN',
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Bangkok',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_user_preferences_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT ck_user_preferences_deadline_hours
        CHECK (deadline_reminder_hours BETWEEN 0 AND 720)
);

CREATE TABLE refresh_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    family_id UUID NOT NULL DEFAULT gen_random_uuid(),
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    replaced_by_id UUID,
    revoke_reason VARCHAR(100),
    user_agent TEXT,
    ip_hash VARCHAR(255),
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_refresh_sessions_token_hash UNIQUE (token_hash),
    CONSTRAINT fk_refresh_sessions_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_refresh_sessions_replaced_by
        FOREIGN KEY (replaced_by_id) REFERENCES refresh_sessions(id) ON DELETE SET NULL,
    CONSTRAINT ck_refresh_sessions_expiry
        CHECK (expires_at > created_at)
);

CREATE INDEX idx_refresh_sessions_user_active
    ON refresh_sessions (user_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX idx_refresh_sessions_family
    ON refresh_sessions (family_id);

CREATE TABLE email_verification_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_email_verification_tokens_hash UNIQUE (token_hash),
    CONSTRAINT fk_email_verification_tokens_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT ck_email_verification_tokens_expiry
        CHECK (expires_at > created_at)
);

CREATE INDEX idx_email_verification_tokens_user
    ON email_verification_tokens (user_id, expires_at);

CREATE TABLE password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_password_reset_tokens_hash UNIQUE (token_hash),
    CONSTRAINT fk_password_reset_tokens_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT ck_password_reset_tokens_expiry
        CHECK (expires_at > created_at)
);

CREATE INDEX idx_password_reset_tokens_user
    ON password_reset_tokens (user_id, expires_at);

CREATE TABLE account_deletion_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    cancel_token_hash VARCHAR(255) NOT NULL,
    reason TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    execute_after TIMESTAMPTZ NOT NULL,
    cancelled_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_code VARCHAR(100),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT uq_account_deletion_cancel_hash UNIQUE (cancel_token_hash),
    CONSTRAINT fk_account_deletion_requests_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT ck_account_deletion_status
        CHECK (status IN ('PENDING', 'CANCELLED', 'COMPLETED', 'FAILED')),
    CONSTRAINT ck_account_deletion_execute_after
        CHECK (execute_after >= requested_at)
);

CREATE UNIQUE INDEX uq_account_deletion_pending_user
    ON account_deletion_requests (user_id)
    WHERE status = 'PENDING';

CREATE INDEX idx_account_deletion_due
    ON account_deletion_requests (execute_after)
    WHERE status = 'PENDING';

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(100),
    target_id UUID,
    outcome VARCHAR(20) NOT NULL,
    trace_id VARCHAR(100),
    ip_address INET,
    user_agent TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_audit_logs_actor
        FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT ck_audit_logs_outcome
        CHECK (outcome IN ('SUCCESS', 'DENIED', 'FAILURE')),
    CONSTRAINT ck_audit_logs_metadata_object
        CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX idx_audit_logs_actor_created
    ON audit_logs (actor_user_id, created_at DESC);

CREATE INDEX idx_audit_logs_target
    ON audit_logs (target_type, target_id, created_at DESC);

CREATE INDEX idx_audit_logs_action_created
    ON audit_logs (action, created_at DESC);

CREATE INDEX idx_audit_logs_trace
    ON audit_logs (trace_id)
    WHERE trace_id IS NOT NULL;

CREATE INDEX idx_audit_logs_metadata_gin
    ON audit_logs USING gin (metadata jsonb_path_ops);

CREATE TABLE external_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    provider VARCHAR(30) NOT NULL,
    provider_account_id VARCHAR(255) NOT NULL,
    provider_account_email CITEXT,
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    token_expires_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    connected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_refreshed_at TIMESTAMPTZ,
    disconnected_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_external_connections_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT ck_external_connections_provider
        CHECK (provider IN ('GOOGLE_DRIVE')),
    CONSTRAINT ck_external_connections_status
        CHECK (status IN ('ACTIVE', 'EXPIRED', 'REVOKED', 'ERROR')),
    CONSTRAINT ck_external_connections_metadata_object
        CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE UNIQUE INDEX uq_external_connections_active_provider
    ON external_connections (user_id, provider)
    WHERE status = 'ACTIVE' AND deleted_at IS NULL;

CREATE UNIQUE INDEX uq_external_connections_provider_account
    ON external_connections (provider, provider_account_id, user_id)
    WHERE deleted_at IS NULL;

-- =========================================================
-- 2. Topics, source documents and quizzes
-- =========================================================

CREATE TABLE topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    visibility VARCHAR(20) NOT NULL DEFAULT 'PRIVATE',
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    published_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector(
            'simple',
            coalesce(title, '') || ' ' || coalesce(description, '')
        )
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_topics_owner
        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT ck_topics_visibility
        CHECK (visibility IN ('PRIVATE', 'PUBLIC')),
    CONSTRAINT ck_topics_status
        CHECK (status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')),
    CONSTRAINT ck_topics_title_not_blank
        CHECK (btrim(title) <> ''),
    CONSTRAINT ck_topics_published_at
        CHECK (status <> 'PUBLISHED' OR published_at IS NOT NULL)
);

CREATE INDEX idx_topics_owner_status
    ON topics (owner_id, status)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_topics_visibility_status
    ON topics (visibility, status, published_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_topics_search_vector
    ON topics USING gin (search_vector);

CREATE INDEX idx_topics_title_trgm
    ON topics USING gin (title gin_trgm_ops);

CREATE TABLE source_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID NOT NULL,
    owner_id UUID NOT NULL,
    external_connection_id UUID,
    source_type VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    original_filename VARCHAR(500),
    display_name VARCHAR(500),
    mime_type VARCHAR(255),
    size_bytes BIGINT,
    checksum_sha256 VARCHAR(64),
    storage_bucket VARCHAR(255),
    storage_key TEXT,
    source_url TEXT,
    external_file_id VARCHAR(255),
    external_modified_at TIMESTAMPTZ,
    extracted_text TEXT,
    language VARCHAR(20),
    error_code VARCHAR(100),
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    processed_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_source_documents_topic
        FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
    CONSTRAINT fk_source_documents_owner
        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_source_documents_external_connection
        FOREIGN KEY (external_connection_id)
        REFERENCES external_connections(id) ON DELETE SET NULL,
    CONSTRAINT ck_source_documents_type
        CHECK (
            source_type IN (
                'PASTE', 'FILE', 'URL', 'GOOGLE_DRIVE',
                'AUDIO', 'IMAGE'
            )
        ),
    CONSTRAINT ck_source_documents_status
        CHECK (
            status IN (
                'PENDING', 'UPLOADED', 'PROCESSING',
                'READY', 'FAILED', 'DELETED'
            )
        ),
    CONSTRAINT ck_source_documents_size
        CHECK (size_bytes IS NULL OR size_bytes BETWEEN 0 AND 52428800),
    CONSTRAINT ck_source_documents_checksum
        CHECK (
            checksum_sha256 IS NULL
            OR checksum_sha256 ~ '^[0-9a-fA-F]{64}$'
        ),
    CONSTRAINT ck_source_documents_ready_text
        CHECK (
            status <> 'READY'
            OR char_length(coalesce(extracted_text, '')) >= 100
        ),
    CONSTRAINT ck_source_documents_metadata_object
        CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX idx_source_documents_topic_status
    ON source_documents (topic_id, status)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_source_documents_owner_created
    ON source_documents (owner_id, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_source_documents_checksum
    ON source_documents (checksum_sha256)
    WHERE checksum_sha256 IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX idx_source_documents_external_file
    ON source_documents (external_connection_id, external_file_id)
    WHERE external_file_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX idx_source_documents_metadata_gin
    ON source_documents USING gin (metadata jsonb_path_ops);

CREATE TABLE source_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL,
    topic_id UUID NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(content, ''))
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_source_chunks_document
        FOREIGN KEY (document_id) REFERENCES source_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_source_chunks_topic
        FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
    CONSTRAINT uq_source_chunks_document_index
        UNIQUE (document_id, chunk_index),
    CONSTRAINT ck_source_chunks_index
        CHECK (chunk_index >= 0),
    CONSTRAINT ck_source_chunks_token_count
        CHECK (token_count IS NULL OR token_count >= 0),
    CONSTRAINT ck_source_chunks_char_range
        CHECK (
            (char_start IS NULL AND char_end IS NULL)
            OR (
                char_start IS NOT NULL
                AND char_end IS NOT NULL
                AND char_start >= 0
                AND char_end >= char_start
            )
        ),
    CONSTRAINT ck_source_chunks_content_not_blank
        CHECK (btrim(content) <> ''),
    CONSTRAINT ck_source_chunks_metadata_object
        CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX idx_source_chunks_topic
    ON source_chunks (topic_id, document_id, chunk_index);

CREATE INDEX idx_source_chunks_search_vector
    ON source_chunks USING gin (search_vector);

CREATE INDEX idx_source_chunks_metadata_gin
    ON source_chunks USING gin (metadata jsonb_path_ops);

CREATE TABLE quizzes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID,
    owner_id UUID NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    visibility VARCHAR(20) NOT NULL DEFAULT 'PRIVATE',
    generation_mode VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    difficulty VARCHAR(20),
    duration_minutes INTEGER,
    generation_error_code VARCHAR(100),
    generation_error_message TEXT,
    published_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_quizzes_topic
        FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE SET NULL,
    CONSTRAINT fk_quizzes_owner
        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT ck_quizzes_status
        CHECK (
            status IN (
                'DRAFT', 'GENERATING', 'READY',
                'PUBLISHED', 'ARCHIVED', 'FAILED'
            )
        ),
    CONSTRAINT ck_quizzes_visibility
        CHECK (visibility IN ('PRIVATE', 'PUBLIC')),
    CONSTRAINT ck_quizzes_generation_mode
        CHECK (generation_mode IN ('MANUAL', 'AI')),
    CONSTRAINT ck_quizzes_difficulty
        CHECK (
            difficulty IS NULL
            OR difficulty IN ('EASY', 'MEDIUM', 'HARD', 'MIXED')
        ),
    CONSTRAINT ck_quizzes_duration
        CHECK (
            duration_minutes IS NULL
            OR duration_minutes BETWEEN 1 AND 1440
        ),
    CONSTRAINT ck_quizzes_title_not_blank
        CHECK (btrim(title) <> ''),
    CONSTRAINT ck_quizzes_publish_state
        CHECK (status <> 'PUBLISHED' OR published_at IS NOT NULL)
);

CREATE INDEX idx_quizzes_owner_status
    ON quizzes (owner_id, status, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_quizzes_topic
    ON quizzes (topic_id, status)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_quizzes_public
    ON quizzes (published_at DESC)
    WHERE visibility = 'PUBLIC'
      AND status = 'PUBLISHED'
      AND deleted_at IS NULL;

CREATE INDEX idx_quizzes_title_trgm
    ON quizzes USING gin (title gin_trgm_ops);

CREATE TABLE quiz_sources (
    quiz_id UUID NOT NULL,
    source_document_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_quiz_sources
        PRIMARY KEY (quiz_id, source_document_id),
    CONSTRAINT fk_quiz_sources_quiz
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
    CONSTRAINT fk_quiz_sources_document
        FOREIGN KEY (source_document_id)
        REFERENCES source_documents(id) ON DELETE CASCADE
);

CREATE INDEX idx_quiz_sources_document
    ON quiz_sources (source_document_id);

CREATE TABLE questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_id UUID NOT NULL,
    source_chunk_id UUID,
    type VARCHAR(30) NOT NULL,
    prompt TEXT NOT NULL,
    explanation TEXT,
    points NUMERIC(8, 2) NOT NULL DEFAULT 1.00,
    position INTEGER NOT NULL,
    difficulty VARCHAR(20),
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_questions_quiz
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
    CONSTRAINT fk_questions_source_chunk
        FOREIGN KEY (source_chunk_id) REFERENCES source_chunks(id) ON DELETE SET NULL,
    CONSTRAINT ck_questions_type
        CHECK (
            type IN (
                'SINGLE_CHOICE', 'MULTIPLE_SELECT', 'FILL_BLANK'
            )
        ),
    CONSTRAINT ck_questions_points
        CHECK (points > 0),
    CONSTRAINT ck_questions_position
        CHECK (position >= 0),
    CONSTRAINT ck_questions_difficulty
        CHECK (
            difficulty IS NULL
            OR difficulty IN ('EASY', 'MEDIUM', 'HARD')
        ),
    CONSTRAINT ck_questions_prompt_not_blank
        CHECK (btrim(prompt) <> '')
);

CREATE UNIQUE INDEX uq_questions_active_position
    ON questions (quiz_id, position)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_questions_quiz_active
    ON questions (quiz_id, position)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_questions_source_chunk
    ON questions (source_chunk_id)
    WHERE source_chunk_id IS NOT NULL;

CREATE TABLE question_options (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID NOT NULL,
    option_text TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL DEFAULT FALSE,
    position INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_question_options_question
        FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
    CONSTRAINT uq_question_options_position
        UNIQUE (question_id, position),
    CONSTRAINT ck_question_options_position
        CHECK (position BETWEEN 0 AND 3),
    CONSTRAINT ck_question_options_text_not_blank
        CHECK (btrim(option_text) <> '')
);

CREATE INDEX idx_question_options_correct
    ON question_options (question_id, position)
    WHERE is_correct = TRUE;

CREATE TABLE accepted_answers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID NOT NULL,
    answer_text TEXT NOT NULL,
    normalized_answer CITEXT NOT NULL,
    position INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_accepted_answers_question
        FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
    CONSTRAINT uq_accepted_answers_position
        UNIQUE (question_id, position),
    CONSTRAINT uq_accepted_answers_normalized
        UNIQUE (question_id, normalized_answer),
    CONSTRAINT ck_accepted_answers_position
        CHECK (position >= 0),
    CONSTRAINT ck_accepted_answers_text_not_blank
        CHECK (btrim(answer_text) <> ''),
    CONSTRAINT ck_accepted_answers_normalized_not_blank
        CHECK (btrim(normalized_answer::text) <> '')
);

-- =========================================================
-- 3. Classrooms and assignments
-- =========================================================

CREATE TABLE classrooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    join_code CITEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    archived_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_classrooms_owner
        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT ck_classrooms_status
        CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    CONSTRAINT ck_classrooms_join_code
        CHECK (join_code::text ~ '^[A-Za-z0-9]{6,12}$'),
    CONSTRAINT ck_classrooms_name_not_blank
        CHECK (btrim(name) <> ''),
    CONSTRAINT ck_classrooms_archived_at
        CHECK (status <> 'ARCHIVED' OR archived_at IS NOT NULL)
);

CREATE UNIQUE INDEX uq_classrooms_active_join_code
    ON classrooms (join_code)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_classrooms_owner
    ON classrooms (owner_id, status)
    WHERE deleted_at IS NULL;

CREATE TABLE classroom_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    classroom_id UUID NOT NULL,
    user_id UUID NOT NULL,
    member_role VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    left_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_classroom_members_classroom
        FOREIGN KEY (classroom_id) REFERENCES classrooms(id) ON DELETE CASCADE,
    CONSTRAINT fk_classroom_members_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uq_classroom_members_user
        UNIQUE (classroom_id, user_id),
    CONSTRAINT ck_classroom_members_role
        CHECK (member_role IN ('TEACHER', 'STUDENT')),
    CONSTRAINT ck_classroom_members_status
        CHECK (status IN ('ACTIVE', 'LEFT', 'REMOVED')),
    CONSTRAINT ck_classroom_members_left_at
        CHECK (status = 'ACTIVE' OR left_at IS NOT NULL)
);

CREATE INDEX idx_classroom_members_user_active
    ON classroom_members (user_id, classroom_id)
    WHERE status = 'ACTIVE';

CREATE INDEX idx_classroom_members_classroom_active
    ON classroom_members (classroom_id, member_role)
    WHERE status = 'ACTIVE';

CREATE TABLE assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    classroom_id UUID NOT NULL,
    quiz_id UUID NOT NULL,
    created_by UUID NOT NULL,
    title VARCHAR(255) NOT NULL,
    instructions TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    opens_at TIMESTAMPTZ,
    due_at TIMESTAMPTZ,
    duration_minutes INTEGER,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    answer_release_policy VARCHAR(30) NOT NULL DEFAULT 'IMMEDIATE',
    published_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_assignments_classroom
        FOREIGN KEY (classroom_id) REFERENCES classrooms(id) ON DELETE CASCADE,
    CONSTRAINT fk_assignments_quiz
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE RESTRICT,
    CONSTRAINT fk_assignments_creator
        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT ck_assignments_status
        CHECK (status IN ('DRAFT', 'PUBLISHED', 'CLOSED', 'ARCHIVED')),
    CONSTRAINT ck_assignments_duration
        CHECK (
            duration_minutes IS NULL
            OR duration_minutes BETWEEN 1 AND 1440
        ),
    CONSTRAINT ck_assignments_max_attempts
        CHECK (max_attempts BETWEEN 1 AND 100),
    CONSTRAINT ck_assignments_release_policy
        CHECK (
            answer_release_policy IN (
                'IMMEDIATE', 'AFTER_DUE_DATE', 'NEVER'
            )
        ),
    CONSTRAINT ck_assignments_window
        CHECK (
            opens_at IS NULL
            OR due_at IS NULL
            OR due_at > opens_at
        ),
    CONSTRAINT ck_assignments_title_not_blank
        CHECK (btrim(title) <> ''),
    CONSTRAINT ck_assignments_published_at
        CHECK (status <> 'PUBLISHED' OR published_at IS NOT NULL)
);

CREATE INDEX idx_assignments_classroom_status
    ON assignments (classroom_id, status, due_at)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_assignments_quiz
    ON assignments (quiz_id)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_assignments_due
    ON assignments (due_at)
    WHERE status = 'PUBLISHED' AND deleted_at IS NULL;

-- =========================================================
-- 4. Attempts and grading
-- =========================================================

CREATE TABLE attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_id UUID NOT NULL,
    user_id UUID NOT NULL,
    assignment_id UUID,
    status VARCHAR(20) NOT NULL DEFAULT 'IN_PROGRESS',
    attempt_number INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deadline_at TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    last_saved_at TIMESTAMPTZ,
    answer_release_policy VARCHAR(30) NOT NULL DEFAULT 'IMMEDIATE',
    timed_out BOOLEAN NOT NULL DEFAULT FALSE,
    submission_idempotency_key VARCHAR(255),
    score NUMERIC(10, 2),
    percentage NUMERIC(7, 4),
    correct_count INTEGER,
    total_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_attempts_quiz
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE RESTRICT,
    CONSTRAINT fk_attempts_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_attempts_assignment
        FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE SET NULL,
    CONSTRAINT ck_attempts_status
        CHECK (
            status IN (
                'IN_PROGRESS', 'SUBMITTED',
                'EXPIRED', 'ABANDONED'
            )
        ),
    CONSTRAINT ck_attempts_number
        CHECK (attempt_number >= 1),
    CONSTRAINT ck_attempts_release_policy
        CHECK (
            answer_release_policy IN (
                'IMMEDIATE', 'AFTER_DUE_DATE', 'NEVER'
            )
        ),
    CONSTRAINT ck_attempts_score
        CHECK (score IS NULL OR score >= 0),
    CONSTRAINT ck_attempts_percentage
        CHECK (percentage IS NULL OR percentage BETWEEN 0 AND 100),
    CONSTRAINT ck_attempts_counts
        CHECK (
            (correct_count IS NULL OR correct_count >= 0)
            AND (total_count IS NULL OR total_count >= 0)
            AND (
                correct_count IS NULL
                OR total_count IS NULL
                OR correct_count <= total_count
            )
        ),
    CONSTRAINT ck_attempts_submission_time
        CHECK (submitted_at IS NULL OR submitted_at >= started_at),
    CONSTRAINT ck_attempts_deadline
        CHECK (deadline_at IS NULL OR deadline_at >= started_at)
);

CREATE UNIQUE INDEX uq_attempts_number
    ON attempts (
        user_id,
        quiz_id,
        COALESCE(assignment_id, '00000000-0000-0000-0000-000000000000'::uuid),
        attempt_number
    );

CREATE UNIQUE INDEX uq_attempts_submission_idempotency
    ON attempts (submission_idempotency_key)
    WHERE submission_idempotency_key IS NOT NULL;

CREATE UNIQUE INDEX uq_attempts_active_assignment_user
    ON attempts (assignment_id, user_id)
    WHERE assignment_id IS NOT NULL AND status = 'IN_PROGRESS';

CREATE INDEX idx_attempts_user_status
    ON attempts (user_id, status, started_at DESC);

CREATE INDEX idx_attempts_assignment
    ON attempts (assignment_id, user_id, attempt_number)
    WHERE assignment_id IS NOT NULL;

CREATE TABLE attempt_question_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id UUID NOT NULL,
    source_question_id UUID,
    source_chunk_id UUID,
    type VARCHAR(30) NOT NULL,
    prompt TEXT NOT NULL,
    explanation TEXT,
    points NUMERIC(8, 2) NOT NULL,
    position INTEGER NOT NULL,
    options_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    answer_key JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_attempt_question_snapshots_attempt
        FOREIGN KEY (attempt_id) REFERENCES attempts(id) ON DELETE CASCADE,
    CONSTRAINT fk_attempt_question_snapshots_question
        FOREIGN KEY (source_question_id) REFERENCES questions(id) ON DELETE SET NULL,
    CONSTRAINT fk_attempt_question_snapshots_chunk
        FOREIGN KEY (source_chunk_id) REFERENCES source_chunks(id) ON DELETE SET NULL,
    CONSTRAINT uq_attempt_question_snapshots_position
        UNIQUE (attempt_id, position),
    CONSTRAINT uq_attempt_question_snapshots_attempt_id_id
        UNIQUE (attempt_id, id),
    CONSTRAINT ck_attempt_question_snapshots_type
        CHECK (
            type IN (
                'SINGLE_CHOICE', 'MULTIPLE_SELECT', 'FILL_BLANK'
            )
        ),
    CONSTRAINT ck_attempt_question_snapshots_points
        CHECK (points > 0),
    CONSTRAINT ck_attempt_question_snapshots_position
        CHECK (position >= 0),
    CONSTRAINT ck_attempt_question_snapshots_options
        CHECK (jsonb_typeof(options_snapshot) = 'array'),
    CONSTRAINT ck_attempt_question_snapshots_answer_key
        CHECK (
            jsonb_typeof(answer_key) IN ('object', 'array', 'string')
        )
);

CREATE INDEX idx_attempt_question_snapshots_attempt
    ON attempt_question_snapshots (attempt_id, position);

CREATE TABLE attempt_answers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id UUID NOT NULL,
    question_snapshot_id UUID NOT NULL,
    selected_option_ids JSONB,
    answer_text TEXT,
    is_correct BOOLEAN,
    awarded_points NUMERIC(8, 2),
    answered_at TIMESTAMPTZ,
    graded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_attempt_answers_attempt
        FOREIGN KEY (attempt_id) REFERENCES attempts(id) ON DELETE CASCADE,
    CONSTRAINT fk_attempt_answers_snapshot
        FOREIGN KEY (attempt_id, question_snapshot_id)
        REFERENCES attempt_question_snapshots(attempt_id, id)
        ON DELETE CASCADE,
    CONSTRAINT uq_attempt_answers_snapshot
        UNIQUE (attempt_id, question_snapshot_id),
    CONSTRAINT ck_attempt_answers_selected_options
        CHECK (
            selected_option_ids IS NULL
            OR jsonb_typeof(selected_option_ids) = 'array'
        ),
    CONSTRAINT ck_attempt_answers_awarded_points
        CHECK (awarded_points IS NULL OR awarded_points >= 0),
    CONSTRAINT ck_attempt_answers_graded_at
        CHECK (
            graded_at IS NULL
            OR answered_at IS NULL
            OR graded_at >= answered_at
        )
);

CREATE INDEX idx_attempt_answers_attempt
    ON attempt_answers (attempt_id);

-- =========================================================
-- 5. Community
-- =========================================================

CREATE TABLE bookmarks (
    user_id UUID NOT NULL,
    quiz_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_bookmarks PRIMARY KEY (user_id, quiz_id),
    CONSTRAINT fk_bookmarks_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_bookmarks_quiz
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
);

CREATE INDEX idx_bookmarks_quiz
    ON bookmarks (quiz_id, created_at DESC);

CREATE TABLE ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    quiz_id UUID NOT NULL,
    attempt_id UUID,
    rating SMALLINT NOT NULL,
    review TEXT,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_ratings_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_ratings_quiz
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
    CONSTRAINT fk_ratings_attempt
        FOREIGN KEY (attempt_id) REFERENCES attempts(id) ON DELETE SET NULL,
    CONSTRAINT ck_ratings_value
        CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT ck_ratings_review_length
        CHECK (review IS NULL OR char_length(review) <= 5000)
);

CREATE UNIQUE INDEX uq_ratings_active_user_quiz
    ON ratings (user_id, quiz_id)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_ratings_quiz_active
    ON ratings (quiz_id, rating, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE TABLE quiz_statistics (
    quiz_id UUID PRIMARY KEY,
    learner_count BIGINT NOT NULL DEFAULT 0,
    attempt_count BIGINT NOT NULL DEFAULT 0,
    rating_count BIGINT NOT NULL DEFAULT 0,
    rating_sum BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_quiz_statistics_quiz
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
    CONSTRAINT ck_quiz_statistics_counts
        CHECK (
            learner_count >= 0
            AND attempt_count >= 0
            AND rating_count >= 0
            AND rating_sum >= 0
            AND rating_sum <= rating_count * 5
        )
);

-- =========================================================
-- 6. Jobs, notifications and outbox
-- =========================================================

CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(40) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'QUEUED',
    subject_user_id UUID,
    resource_type VARCHAR(100),
    resource_id UUID,
    idempotency_key VARCHAR(255),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB,
    priority INTEGER NOT NULL DEFAULT 100,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at TIMESTAMPTZ,
    locked_by VARCHAR(255),
    heartbeat_at TIMESTAMPTZ,
    error_code VARCHAR(100),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_jobs_subject_user
        FOREIGN KEY (subject_user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT uq_jobs_idempotency_key UNIQUE (idempotency_key),
    CONSTRAINT ck_jobs_type
        CHECK (
            type IN (
                'DOCUMENT_INGESTION', 'QUIZ_GENERATION',
                'CHAT_RESPONSE', 'EXPORT', 'ACCOUNT_DELETION'
            )
        ),
    CONSTRAINT ck_jobs_status
    CHECK (
        status IN (
            'QUEUED', 'RUNNING', 'SUCCEEDED',
            'RETRY', 'FAILED', 'CANCELLED'
        )
    ),
    CONSTRAINT ck_jobs_priority
        CHECK (priority >= 0),
    CONSTRAINT ck_jobs_attempts
        CHECK (
            attempts >= 0
            AND max_attempts >= 1
            AND attempts <= max_attempts
        ),
    CONSTRAINT ck_jobs_payload_object
        CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_jobs_result_object
        CHECK (result IS NULL OR jsonb_typeof(result) IN ('object', 'array'))
);

CREATE INDEX idx_jobs_poll
    ON jobs (priority ASC, available_at ASC, created_at ASC)
    WHERE status IN ('QUEUED', 'RETRY');

CREATE INDEX idx_jobs_locked
    ON jobs (locked_at, heartbeat_at)
    WHERE status = 'RUNNING';

CREATE INDEX idx_jobs_resource
    ON jobs (resource_type, resource_id, created_at DESC);

CREATE INDEX idx_jobs_subject_user
    ON jobs (subject_user_id, created_at DESC)
    WHERE subject_user_id IS NOT NULL;

CREATE INDEX idx_jobs_payload_gin
    ON jobs USING gin (payload jsonb_path_ops);

CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    related_resource_type VARCHAR(100),
    related_resource_id UUID,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    dedup_key VARCHAR(255),
    email_requested BOOLEAN NOT NULL DEFAULT FALSE,
    email_sent_at TIMESTAMPTZ,
    email_failed_at TIMESTAMPTZ,
    email_error_code VARCHAR(100),
    read_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_notifications_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT ck_notifications_data_object
        CHECK (jsonb_typeof(data) = 'object'),
    CONSTRAINT ck_notifications_email_state
        CHECK (
            NOT (
                email_sent_at IS NOT NULL
                AND email_failed_at IS NOT NULL
            )
        )
);

CREATE UNIQUE INDEX uq_notifications_user_dedup
    ON notifications (user_id, dedup_key)
    WHERE dedup_key IS NOT NULL;

CREATE INDEX idx_notifications_unread
    ON notifications (user_id, created_at DESC)
    WHERE read_at IS NULL;

CREATE INDEX idx_notifications_expiry
    ON notifications (expires_at)
    WHERE expires_at IS NOT NULL;

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    dedup_key VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 10,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at TIMESTAMPTZ,
    locked_by VARCHAR(255),
    published_at TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    last_error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT uq_outbox_events_dedup_key UNIQUE (dedup_key),
    CONSTRAINT ck_outbox_events_status
        CHECK (
            status IN (
                'PENDING', 'PROCESSING', 'PUBLISHED',
                'RETRY', 'DEAD_LETTER'
            )
        ),
    CONSTRAINT ck_outbox_events_attempts
        CHECK (
            attempts >= 0
            AND max_attempts >= 1
            AND attempts <= max_attempts
        ),
    CONSTRAINT ck_outbox_events_payload
        CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_outbox_events_published_at
        CHECK (status <> 'PUBLISHED' OR published_at IS NOT NULL)
);

CREATE INDEX idx_outbox_events_poll
    ON outbox_events (available_at ASC, created_at ASC)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX idx_outbox_events_aggregate
    ON outbox_events (aggregate_type, aggregate_id, created_at ASC);

CREATE INDEX idx_outbox_events_locked
    ON outbox_events (locked_at)
    WHERE status = 'PROCESSING';

-- =========================================================
-- 7. AI chat and citations
-- =========================================================

CREATE TABLE chat_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    topic_id UUID,
    quiz_id UUID,
    attempt_id UUID,
    title VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP + INTERVAL '90 days'),
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_chat_threads_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_chat_threads_topic
        FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
    CONSTRAINT fk_chat_threads_quiz
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
    CONSTRAINT fk_chat_threads_attempt
        FOREIGN KEY (attempt_id) REFERENCES attempts(id) ON DELETE CASCADE,
    CONSTRAINT ck_chat_threads_status
        CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    CONSTRAINT ck_chat_threads_exactly_one_context
        CHECK (num_nonnulls(topic_id, quiz_id, attempt_id) = 1),
    CONSTRAINT ck_chat_threads_expiry
        CHECK (expires_at > created_at)
);

CREATE INDEX idx_chat_threads_user_active
    ON chat_threads (user_id, updated_at DESC)
    WHERE status = 'ACTIVE' AND deleted_at IS NULL;

CREATE INDEX idx_chat_threads_topic
    ON chat_threads (topic_id)
    WHERE topic_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX idx_chat_threads_quiz
    ON chat_threads (quiz_id)
    WHERE quiz_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX idx_chat_threads_attempt
    ON chat_threads (attempt_id)
    WHERE attempt_id IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL,
    job_id UUID,
    role VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'COMPLETED',
    content TEXT NOT NULL,
    model VARCHAR(100),
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    error_code VARCHAR(100),
    error_message TEXT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_chat_messages_thread
        FOREIGN KEY (thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE,
    CONSTRAINT fk_chat_messages_job
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL,
    CONSTRAINT uq_chat_messages_job UNIQUE (job_id),
    CONSTRAINT ck_chat_messages_role
        CHECK (role IN ('USER', 'ASSISTANT', 'SYSTEM')),
    CONSTRAINT ck_chat_messages_status
        CHECK (
            status IN ('PENDING', 'STREAMING', 'COMPLETED', 'FAILED')
        ),
    CONSTRAINT ck_chat_messages_tokens
        CHECK (
            (input_tokens IS NULL OR input_tokens >= 0)
            AND (output_tokens IS NULL OR output_tokens >= 0)
            AND (total_tokens IS NULL OR total_tokens >= 0)
        ),
    CONSTRAINT ck_chat_messages_content
        CHECK (
            status = 'FAILED'
            OR btrim(content) <> ''
        ),
    CONSTRAINT ck_chat_messages_completed_at
        CHECK (
            status NOT IN ('COMPLETED', 'FAILED')
            OR completed_at IS NOT NULL
        )
);

CREATE INDEX idx_chat_messages_thread_created
    ON chat_messages (thread_id, created_at ASC);

CREATE TABLE chat_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL,
    source_chunk_id UUID NOT NULL,
    citation_index INTEGER NOT NULL,
    quote_excerpt TEXT,
    relevance_score DOUBLE PRECISION,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_chat_citations_message
        FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
    CONSTRAINT fk_chat_citations_chunk
        FOREIGN KEY (source_chunk_id) REFERENCES source_chunks(id) ON DELETE CASCADE,
    CONSTRAINT uq_chat_citations_message_index
        UNIQUE (message_id, citation_index),
    CONSTRAINT uq_chat_citations_message_chunk
        UNIQUE (message_id, source_chunk_id),
    CONSTRAINT ck_chat_citations_index
        CHECK (citation_index >= 0),
    CONSTRAINT ck_chat_citations_relevance
        CHECK (
            relevance_score IS NULL
            OR relevance_score BETWEEN -1.0 AND 1.0
        ),
    CONSTRAINT ck_chat_citations_metadata
        CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX idx_chat_citations_chunk
    ON chat_citations (source_chunk_id);

-- =========================================================
-- 8. Export
-- =========================================================

CREATE TABLE exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    quiz_id UUID,
    attempt_id UUID,
    job_id UUID,
    format VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    include_answers BOOLEAN NOT NULL DEFAULT FALSE,
    storage_bucket VARCHAR(255),
    storage_key TEXT,
    filename VARCHAR(500),
    mime_type VARCHAR(255),
    file_size_bytes BIGINT,
    checksum_sha256 VARCHAR(64),
    expires_at TIMESTAMPTZ,
    downloaded_at TIMESTAMPTZ,
    error_code VARCHAR(100),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT fk_exports_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_exports_quiz
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
    CONSTRAINT fk_exports_attempt
        FOREIGN KEY (attempt_id) REFERENCES attempts(id) ON DELETE CASCADE,
    CONSTRAINT fk_exports_job
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL,
    CONSTRAINT uq_exports_job UNIQUE (job_id),
    CONSTRAINT ck_exports_exactly_one_source
        CHECK (num_nonnulls(quiz_id, attempt_id) = 1),
    CONSTRAINT ck_exports_format
        CHECK (format IN ('PDF', 'DOCX', 'CSV')),
    CONSTRAINT ck_exports_status
        CHECK (
            status IN (
                'PENDING', 'PROCESSING', 'READY',
                'FAILED', 'EXPIRED'
            )
        ),
    CONSTRAINT ck_exports_size
        CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
    CONSTRAINT ck_exports_checksum
        CHECK (
            checksum_sha256 IS NULL
            OR checksum_sha256 ~ '^[0-9a-fA-F]{64}$'
        ),
    CONSTRAINT ck_exports_ready_storage
        CHECK (
            status <> 'READY'
            OR (
                storage_bucket IS NOT NULL
                AND storage_key IS NOT NULL
                AND filename IS NOT NULL
                AND expires_at IS NOT NULL
            )
        )
);

CREATE INDEX idx_exports_user_created
    ON exports (user_id, created_at DESC);

CREATE INDEX idx_exports_expiry
    ON exports (expires_at)
    WHERE status = 'READY';

CREATE INDEX idx_exports_quiz
    ON exports (quiz_id)
    WHERE quiz_id IS NOT NULL;

CREATE INDEX idx_exports_attempt
    ON exports (attempt_id)
    WHERE attempt_id IS NOT NULL;

-- =========================================================
-- updated_at triggers
-- =========================================================

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_preferences_updated_at
BEFORE UPDATE ON user_preferences
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_account_deletion_requests_updated_at
BEFORE UPDATE ON account_deletion_requests
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_external_connections_updated_at
BEFORE UPDATE ON external_connections
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_topics_updated_at
BEFORE UPDATE ON topics
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_source_documents_updated_at
BEFORE UPDATE ON source_documents
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_quizzes_updated_at
BEFORE UPDATE ON quizzes
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_questions_updated_at
BEFORE UPDATE ON questions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_question_options_updated_at
BEFORE UPDATE ON question_options
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_classrooms_updated_at
BEFORE UPDATE ON classrooms
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_classroom_members_updated_at
BEFORE UPDATE ON classroom_members
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_assignments_updated_at
BEFORE UPDATE ON assignments
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_attempts_updated_at
BEFORE UPDATE ON attempts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_attempt_answers_updated_at
BEFORE UPDATE ON attempt_answers
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_ratings_updated_at
BEFORE UPDATE ON ratings
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_quiz_statistics_updated_at
BEFORE UPDATE ON quiz_statistics
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_jobs_updated_at
BEFORE UPDATE ON jobs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_outbox_events_updated_at
BEFORE UPDATE ON outbox_events
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_chat_threads_updated_at
BEFORE UPDATE ON chat_threads
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_exports_updated_at
BEFORE UPDATE ON exports
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
