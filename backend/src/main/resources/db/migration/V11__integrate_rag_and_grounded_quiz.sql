ALTER TABLE source_documents DROP CONSTRAINT IF EXISTS ck_source_documents_status;
UPDATE source_documents SET status = CASE status
    WHEN 'PENDING' THEN 'UPLOADED'
    WHEN 'PROCESSING' THEN 'EMBEDDING'
    ELSE status END
WHERE status IN ('PENDING', 'PROCESSING');
ALTER TABLE source_documents ADD CONSTRAINT ck_source_documents_status CHECK (status IN (
    'UPLOADED', 'SCANNING', 'EXTRACTING', 'EMBEDDING', 'READY', 'FAILED', 'DELETED'
));

ALTER TABLE source_documents
    ADD COLUMN IF NOT EXISTS rag_document_id UUID,
    ADD COLUMN IF NOT EXISTS rag_job_id UUID,
    ADD COLUMN IF NOT EXISTS indexing_progress INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS indexing_step VARCHAR(64),
    ADD COLUMN IF NOT EXISTS page_count INTEGER,
    ADD COLUMN IF NOT EXISTS chunk_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ;
ALTER TABLE source_documents DROP CONSTRAINT IF EXISTS ck_source_documents_indexing_progress;
ALTER TABLE source_documents ADD CONSTRAINT ck_source_documents_indexing_progress
    CHECK (indexing_progress BETWEEN 0 AND 100);
CREATE INDEX IF NOT EXISTS idx_source_documents_rag_document
    ON source_documents (rag_document_id) WHERE rag_document_id IS NOT NULL;

ALTER TABLE quiz_sources ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid();
ALTER TABLE quiz_sources ALTER COLUMN id SET NOT NULL;
ALTER TABLE quiz_sources DROP CONSTRAINT IF EXISTS pk_quiz_sources;
ALTER TABLE quiz_sources ADD CONSTRAINT pk_quiz_sources PRIMARY KEY (id);
ALTER TABLE quiz_sources DROP CONSTRAINT IF EXISTS uq_quiz_sources_quiz_document;
ALTER TABLE quiz_sources ADD CONSTRAINT uq_quiz_sources_quiz_document UNIQUE (quiz_id, source_document_id);

ALTER TABLE source_chunks
    ADD COLUMN IF NOT EXISTS page_number INTEGER,
    ADD COLUMN IF NOT EXISTS slide_number INTEGER,
    ADD COLUMN IF NOT EXISTS heading VARCHAR(1000);

CREATE TABLE IF NOT EXISTS question_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    source_chunk_id UUID NOT NULL REFERENCES source_chunks(id) ON DELETE RESTRICT,
    citation_role VARCHAR(20) NOT NULL,
    evidence_quote TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_question_citations_role CHECK (citation_role IN ('QUESTION', 'ANSWER', 'EXPLANATION')),
    CONSTRAINT ck_question_citations_quote CHECK (btrim(evidence_quote) <> ''),
    CONSTRAINT uq_question_citations_position UNIQUE (question_id, citation_role, position)
);
CREATE INDEX IF NOT EXISTS idx_question_citations_question ON question_citations (question_id, citation_role, position);

ALTER TABLE attempt_question_snapshots
    ADD COLUMN IF NOT EXISTS citations_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE attempt_question_snapshots DROP CONSTRAINT IF EXISTS ck_attempt_question_snapshots_citations;
ALTER TABLE attempt_question_snapshots ADD CONSTRAINT ck_attempt_question_snapshots_citations
    CHECK (jsonb_typeof(citations_snapshot) = 'array');

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS progress_percent INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS current_step VARCHAR(64);
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_progress_percent;
ALTER TABLE jobs ADD CONSTRAINT ck_jobs_progress_percent CHECK (progress_percent BETWEEN 0 AND 100);
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_type;
ALTER TABLE jobs ADD CONSTRAINT ck_jobs_type CHECK (type IN (
    'SOURCE_INGESTION', 'RAG_INDEX_POLL', 'QUIZ_GENERATION', 'CHAT_RESPONSE',
    'EXPORT', 'ACCOUNT_DELETION', 'AUTH_EMAIL'
));
