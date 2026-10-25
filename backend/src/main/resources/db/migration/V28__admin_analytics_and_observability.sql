-- Administrative product analytics. Raw events are append-only and daily tables
-- are replaceable projections, so a bounded date range can be recomputed safely.
CREATE TABLE product_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(80) NOT NULL,
    user_id UUID,
    session_id VARCHAR(120),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT fk_product_events_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT ck_product_events_properties CHECK (jsonb_typeof(properties) = 'object')
);

CREATE INDEX idx_product_events_time ON product_events(occurred_at DESC);
CREATE INDEX idx_product_events_user_time ON product_events(user_id, occurred_at DESC)
    WHERE user_id IS NOT NULL;
CREATE INDEX idx_product_events_type_time ON product_events(event_type, occurred_at DESC);

CREATE TABLE daily_platform_metrics (
    metric_date DATE PRIMARY KEY,
    active_users BIGINT NOT NULL DEFAULT 0,
    new_users BIGINT NOT NULL DEFAULT 0,
    activated_users BIGINT NOT NULL DEFAULT 0,
    quizzes_created BIGINT NOT NULL DEFAULT 0,
    ai_quizzes_generated BIGINT NOT NULL DEFAULT 0,
    quizzes_completed BIGINT NOT NULL DEFAULT 0,
    documents_uploaded BIGINT NOT NULL DEFAULT 0,
    documents_ingested BIGINT NOT NULL DEFAULT 0,
    ai_requests BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE daily_user_metrics (
    metric_date DATE NOT NULL,
    user_id UUID NOT NULL,
    event_count BIGINT NOT NULL DEFAULT 0,
    quiz_count BIGINT NOT NULL DEFAULT 0,
    ai_request_count BIGINT NOT NULL DEFAULT 0,
    ai_cost NUMERIC(16,6) NOT NULL DEFAULT 0,
    PRIMARY KEY(metric_date, user_id),
    CONSTRAINT fk_daily_user_metrics_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_daily_user_metrics_cost ON daily_user_metrics(metric_date, ai_cost DESC);

CREATE TABLE daily_ai_metrics (
    metric_date DATE NOT NULL,
    provider VARCHAR(60) NOT NULL DEFAULT 'unknown',
    model VARCHAR(120) NOT NULL DEFAULT 'unknown',
    request_count BIGINT NOT NULL DEFAULT 0,
    success_count BIGINT NOT NULL DEFAULT 0,
    failure_count BIGINT NOT NULL DEFAULT 0,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    estimated_cost NUMERIC(16,6) NOT NULL DEFAULT 0,
    actual_cost NUMERIC(16,6) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(metric_date, provider, model)
);

CREATE TABLE daily_security_metrics (
    metric_date DATE NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    event_count BIGINT NOT NULL DEFAULT 0,
    prevented_cost NUMERIC(16,6) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(metric_date, event_type)
);

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS ai_actual_cost NUMERIC(14,6);
ALTER TABLE account_reputations ADD COLUMN IF NOT EXISTS daily_quota_override INTEGER;
ALTER TABLE account_reputations ADD COLUMN IF NOT EXISTS daily_cost_budget_override NUMERIC(14,6);
ALTER TABLE account_reputations ADD COLUMN IF NOT EXISTS service_level_override VARCHAR(20);
ALTER TABLE account_reputations ADD CONSTRAINT ck_account_reputations_quota_override
    CHECK (daily_quota_override IS NULL OR daily_quota_override >= 0);
ALTER TABLE account_reputations ADD CONSTRAINT ck_account_reputations_budget_override
    CHECK (daily_cost_budget_override IS NULL OR daily_cost_budget_override >= 0);
ALTER TABLE account_reputations ADD CONSTRAINT ck_account_reputations_level_override
    CHECK (service_level_override IS NULL OR service_level_override IN ('TRUSTED','NORMAL','CAUTION','RESTRICTED','BLOCKED'));

CREATE OR REPLACE FUNCTION bkquiz_product_event() RETURNS trigger AS $$
DECLARE
    payload JSONB := to_jsonb(NEW);
    actor UUID;
    kind TEXT := TG_ARGV[0];
BEGIN
    actor := NULLIF(COALESCE(payload->>'owner_id', payload->>'user_id',
        payload->>'subject_user_id', payload->>'id'), '')::uuid;
    IF TG_TABLE_NAME = 'attempt_answers' THEN
        SELECT user_id INTO actor FROM attempts WHERE id = (payload->>'attempt_id')::uuid;
    END IF;
    INSERT INTO product_events(event_type, user_id, properties)
    VALUES (kind, actor, jsonb_strip_nulls(jsonb_build_object(
        'resourceId', COALESCE(payload->>'id', payload->>'resource_id'),
        'resourceType', TG_TABLE_NAME,
        'model', payload->>'ai_model',
        'estimatedCost', payload->>'ai_estimated_cost',
        'actualCost', payload->>'ai_actual_cost',
        'status', payload->>'status')));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_product_user_registered AFTER INSERT ON users
    FOR EACH ROW EXECUTE FUNCTION bkquiz_product_event('USER_REGISTERED');
CREATE TRIGGER trg_product_user_activated AFTER UPDATE OF email_verified_at ON users
    FOR EACH ROW WHEN (OLD.email_verified_at IS NULL AND NEW.email_verified_at IS NOT NULL)
    EXECUTE FUNCTION bkquiz_product_event('USER_ACTIVATED');
CREATE TRIGGER trg_product_document_uploaded AFTER INSERT ON source_documents
    FOR EACH ROW EXECUTE FUNCTION bkquiz_product_event('DOCUMENT_UPLOADED');
CREATE TRIGGER trg_product_document_ingested AFTER UPDATE OF status ON source_documents
    FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status = 'READY')
    EXECUTE FUNCTION bkquiz_product_event('DOCUMENT_INGESTED');
CREATE TRIGGER trg_product_quiz_created AFTER INSERT ON quizzes
    FOR EACH ROW EXECUTE FUNCTION bkquiz_product_event('QUIZ_CREATED');
CREATE TRIGGER trg_product_question_answered AFTER INSERT OR UPDATE OF answered_at ON attempt_answers
    FOR EACH ROW WHEN (NEW.answered_at IS NOT NULL)
    EXECUTE FUNCTION bkquiz_product_event('QUESTION_ANSWERED');
CREATE TRIGGER trg_product_quiz_completed AFTER UPDATE OF status ON attempts
    FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status = 'SUBMITTED')
    EXECUTE FUNCTION bkquiz_product_event('QUIZ_COMPLETED');
CREATE TRIGGER trg_product_class_created AFTER INSERT ON classrooms
    FOR EACH ROW EXECUTE FUNCTION bkquiz_product_event('CLASS_CREATED');
CREATE TRIGGER trg_product_class_joined AFTER INSERT ON classroom_members
    FOR EACH ROW EXECUTE FUNCTION bkquiz_product_event('CLASS_JOINED');
CREATE TRIGGER trg_product_ai_job AFTER UPDATE OF status ON jobs
    FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status IN ('SUCCEEDED','FAILED')
        AND NEW.type IN ('QUIZ_GENERATION','CHAT_RESPONSE'))
    EXECUTE FUNCTION bkquiz_product_event('AI_REQUEST_COMPLETED');

CREATE OR REPLACE FUNCTION bkquiz_quiz_generated_event() RETURNS trigger AS $$
BEGIN
    IF NEW.status = 'SUCCEEDED' AND NEW.type = 'QUIZ_GENERATION' THEN
        INSERT INTO product_events(event_type,user_id,properties)
        VALUES ('AI_QUIZ_GENERATED', NEW.subject_user_id,
            jsonb_strip_nulls(jsonb_build_object('resourceId',NEW.resource_id,'model',NEW.ai_model,
            'estimatedCost',NEW.ai_estimated_cost,'actualCost',NEW.ai_actual_cost)));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_product_ai_quiz AFTER UPDATE OF status ON jobs
    FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION bkquiz_quiz_generated_event();

CREATE OR REPLACE FUNCTION bkquiz_risk_product_event() RETURNS trigger AS $$
BEGIN
    INSERT INTO product_events(event_type,user_id,properties)
    VALUES (CASE WHEN NEW.event_type='RATE_LIMIT_TRIGGERED' AND NEW.metadata->>'dimension'='DAILY_QUOTA'
                 THEN 'AI_QUOTA_EXHAUSTED' ELSE 'SECURITY_EVENT' END,
            NEW.user_id, jsonb_build_object('riskEventType',NEW.event_type,'severity',NEW.severity,
                'dimension',NEW.metadata->>'dimension'));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_product_risk_event AFTER INSERT ON risk_events
    FOR EACH ROW EXECUTE FUNCTION bkquiz_risk_product_event();

COMMENT ON TABLE product_events IS 'Append-only, non-sensitive product telemetry written in the domain transaction.';
COMMENT ON TABLE daily_platform_metrics IS 'Idempotently recomputed UTC daily product metrics.';
