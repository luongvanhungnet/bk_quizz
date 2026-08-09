ALTER TABLE source_documents
    ADD COLUMN math_extraction_status VARCHAR(20) NOT NULL DEFAULT 'NOT_DETECTED',
    ADD COLUMN math_formula_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN math_warning_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE source_documents
    ADD CONSTRAINT ck_source_documents_math_status
        CHECK (math_extraction_status IN ('NOT_DETECTED','ENHANCED','PARTIAL','FAILED')),
    ADD CONSTRAINT ck_source_documents_math_counts
        CHECK (math_formula_count >= 0 AND math_warning_count >= 0);

ALTER TABLE source_chunks
    ADD COLUMN raw_content TEXT,
    ADD COLUMN math_enhanced BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE source_chunks SET raw_content = content WHERE raw_content IS NULL;
