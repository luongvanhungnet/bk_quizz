CREATE TABLE stored_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID REFERENCES users(id) ON DELETE SET NULL,
    purpose VARCHAR(40) NOT NULL,
    provider VARCHAR(20) NOT NULL,
    storage_path VARCHAR(1000) NOT NULL,
    original_name VARCHAR(255) NOT NULL,
    declared_media_type VARCHAR(255),
    detected_media_type VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'READY',
    public_access BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_stored_files_provider_path UNIQUE(provider, storage_path),
    CONSTRAINT ck_stored_files_purpose CHECK (purpose IN ('SOURCE','CLASSROOM_ATTACHMENT','AVATAR')),
    CONSTRAINT ck_stored_files_provider CHECK (provider IN ('LOCAL','S3')),
    CONSTRAINT ck_stored_files_status CHECK (status IN ('STAGED','READY','QUARANTINED','DELETED')),
    CONSTRAINT ck_stored_files_size CHECK (size_bytes >= 0)
);
CREATE INDEX idx_stored_files_owner_created ON stored_files(owner_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_stored_files_status ON stored_files(status, created_at);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='source_documents' AND column_name='mime_type')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='source_documents' AND column_name='media_type') THEN
        ALTER TABLE source_documents RENAME COLUMN mime_type TO media_type;
    END IF;
END $$;

ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_file_id UUID REFERENCES stored_files(id) ON DELETE SET NULL;
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS file_id UUID REFERENCES stored_files(id) ON DELETE SET NULL;
ALTER TABLE classroom_attachments ADD COLUMN IF NOT EXISTS file_id UUID REFERENCES stored_files(id) ON DELETE SET NULL;

INSERT INTO stored_files(id, owner_id, purpose, provider, storage_path, original_name,
                         declared_media_type, detected_media_type, size_bytes, sha256, status, public_access, created_at, updated_at)
SELECT gen_random_uuid(), owner_id, 'SOURCE', 'S3', storage_key, coalesce(display_name, original_filename, 'source'),
       media_type, coalesce(media_type, 'application/octet-stream'), coalesce(size_bytes, 0),
       repeat('0', 64), 'READY', false, created_at, updated_at
FROM source_documents WHERE storage_key IS NOT NULL
ON CONFLICT (provider, storage_path) DO NOTHING;
UPDATE source_documents s SET file_id=f.id FROM stored_files f
WHERE s.storage_key=f.storage_path AND f.provider='S3' AND f.purpose='SOURCE' AND s.file_id IS NULL;

INSERT INTO stored_files(id, owner_id, purpose, provider, storage_path, original_name,
                         declared_media_type, detected_media_type, size_bytes, sha256, status, public_access, created_at, updated_at)
SELECT gen_random_uuid(), uploader_id, 'CLASSROOM_ATTACHMENT', 'S3', object_key, original_name,
       media_type, media_type, size_bytes, repeat('0', 64), 'READY', false, created_at, created_at
FROM classroom_attachments WHERE object_key IS NOT NULL
ON CONFLICT (provider, storage_path) DO NOTHING;
UPDATE classroom_attachments a SET file_id=f.id FROM stored_files f
WHERE a.object_key=f.storage_path AND f.provider='S3' AND f.purpose='CLASSROOM_ATTACHMENT' AND a.file_id IS NULL;

ALTER TABLE topics ADD COLUMN IF NOT EXISTS moderation_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE topics ADD COLUMN IF NOT EXISTS moderated_by UUID REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE topics ADD COLUMN IF NOT EXISTS moderated_at TIMESTAMPTZ;
ALTER TABLE topics ADD COLUMN IF NOT EXISTS moderation_reason VARCHAR(1000);
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS moderation_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS moderated_by UUID REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS moderated_at TIMESTAMPTZ;
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS moderation_reason VARCHAR(1000);
ALTER TABLE classrooms ADD COLUMN IF NOT EXISTS moderation_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE classrooms ADD COLUMN IF NOT EXISTS moderated_by UUID REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE classrooms ADD COLUMN IF NOT EXISTS moderated_at TIMESTAMPTZ;
ALTER TABLE classrooms ADD COLUMN IF NOT EXISTS moderation_reason VARCHAR(1000);

ALTER TABLE topics ADD CONSTRAINT ck_topics_moderation_status CHECK (moderation_status IN ('ACTIVE','HIDDEN'));
ALTER TABLE quizzes ADD CONSTRAINT ck_quizzes_moderation_status CHECK (moderation_status IN ('ACTIVE','HIDDEN'));
ALTER TABLE classrooms ADD CONSTRAINT ck_classrooms_moderation_status CHECK (moderation_status IN ('ACTIVE','HIDDEN'));
