CREATE TABLE risk_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    risk_delta NUMERIC(6,5) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_risk_events_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT ck_risk_events_severity CHECK (severity IN ('INFO','LOW','MEDIUM','HIGH','CRITICAL')),
    CONSTRAINT ck_risk_events_delta CHECK (risk_delta >= -1 AND risk_delta <= 1),
    CONSTRAINT ck_risk_events_metadata CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX idx_risk_events_user_created ON risk_events(user_id, created_at DESC);
CREATE INDEX idx_risk_events_type_created ON risk_events(event_type, created_at DESC);

CREATE TABLE account_reputations (
    user_id UUID PRIMARY KEY,
    trust_score INTEGER NOT NULL DEFAULT 20,
    risk_score NUMERIC(6,5) NOT NULL DEFAULT 0,
    service_level VARCHAR(20) NOT NULL DEFAULT 'CAUTION',
    legitimate_activity_count INTEGER NOT NULL DEFAULT 0,
    successful_session_count INTEGER NOT NULL DEFAULT 0,
    ai_operation_count INTEGER NOT NULL DEFAULT 0,
    ai_cost_total NUMERIC(14,6) NOT NULL DEFAULT 0,
    last_calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT fk_account_reputations_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT ck_account_reputations_trust CHECK (trust_score BETWEEN 0 AND 100),
    CONSTRAINT ck_account_reputations_risk CHECK (risk_score BETWEEN 0 AND 1),
    CONSTRAINT ck_account_reputations_level CHECK (service_level IN ('TRUSTED','NORMAL','CAUTION','RESTRICTED','BLOCKED')),
    CONSTRAINT ck_account_reputations_counts CHECK (legitimate_activity_count >= 0 AND successful_session_count >= 0 AND ai_operation_count >= 0),
    CONSTRAINT ck_account_reputations_cost CHECK (ai_cost_total >= 0)
);

INSERT INTO account_reputations(user_id)
SELECT id FROM users WHERE deleted_at IS NULL
ON CONFLICT (user_id) DO NOTHING;

ALTER TABLE jobs ADD COLUMN ai_ip_hash VARCHAR(64);
ALTER TABLE jobs ADD COLUMN ai_device_hash VARCHAR(64);
ALTER TABLE jobs ADD COLUMN ai_lease_id UUID;
ALTER TABLE jobs ADD COLUMN ai_endpoint VARCHAR(120);
ALTER TABLE jobs ADD COLUMN ai_model VARCHAR(120);
ALTER TABLE jobs ADD COLUMN ai_estimated_cost NUMERIC(14,6);
ALTER TABLE jobs ADD COLUMN ai_concurrency_reserved BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX idx_jobs_ai_reserved ON jobs(subject_user_id, status)
WHERE ai_concurrency_reserved = TRUE;
