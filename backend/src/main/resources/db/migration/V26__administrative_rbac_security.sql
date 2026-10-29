-- Production-oriented administrative RBAC. The legacy users.role column remains
-- the STUDENT/TEACHER account type compatibility field.

CREATE TABLE roles (
    code VARCHAR(32) PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    privileged BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE permissions (
    code VARCHAR(80) PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_roles (
    user_id UUID NOT NULL,
    role_code VARCHAR(32) NOT NULL,
    granted_by UUID,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_code),
    CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_roles_role FOREIGN KEY (role_code) REFERENCES roles(code) ON DELETE RESTRICT,
    CONSTRAINT fk_user_roles_granted_by FOREIGN KEY (granted_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE role_permissions (
    role_code VARCHAR(32) NOT NULL,
    permission_code VARCHAR(80) NOT NULL,
    PRIMARY KEY (role_code, permission_code),
    CONSTRAINT fk_role_permissions_role FOREIGN KEY (role_code) REFERENCES roles(code) ON DELETE CASCADE,
    CONSTRAINT fk_role_permissions_permission FOREIGN KEY (permission_code) REFERENCES permissions(code) ON DELETE CASCADE
);

CREATE INDEX idx_user_roles_role ON user_roles(role_code, user_id);
CREATE INDEX idx_role_permissions_permission ON role_permissions(permission_code, role_code);

INSERT INTO roles(code, description, privileged) VALUES
    ('USER', 'Normal authenticated application user', FALSE),
    ('SUPPORT', 'Read-only user support', TRUE),
    ('ANALYST', 'Administrative analytics reader', TRUE),
    ('MODERATOR', 'User and risk moderator', TRUE),
    ('ADMIN', 'Administrative operator', TRUE),
    ('OWNER', 'System owner', TRUE)
ON CONFLICT (code) DO UPDATE SET description = EXCLUDED.description, privileged = EXCLUDED.privileged;

INSERT INTO permissions(code, description) VALUES
    ('analytics:read', 'Read administrative analytics'),
    ('user:read', 'Read user administration data'),
    ('user:suspend', 'Suspend user accounts'),
    ('user:ban', 'Ban user accounts'),
    ('quota:read', 'Read quotas'),
    ('quota:update', 'Update quotas'),
    ('risk:read', 'Read risk data'),
    ('risk:update', 'Update risk controls'),
    ('audit:read', 'Read immutable security audit records'),
    ('admin:read', 'Read administrative resources'),
    ('admin:grant', 'Grant privileged roles'),
    ('admin:revoke', 'Revoke privileged roles'),
    ('system:config', 'Change protected system configuration')
ON CONFLICT (code) DO UPDATE SET description = EXCLUDED.description;

INSERT INTO role_permissions(role_code, permission_code) VALUES
    ('SUPPORT', 'user:read'),
    ('ANALYST', 'analytics:read'),
    ('MODERATOR', 'user:read'), ('MODERATOR', 'user:suspend'),
    ('MODERATOR', 'user:ban'), ('MODERATOR', 'risk:read'),
    ('ADMIN', 'analytics:read'), ('ADMIN', 'user:read'),
    ('ADMIN', 'user:suspend'), ('ADMIN', 'user:ban'),
    ('ADMIN', 'quota:read'), ('ADMIN', 'quota:update'),
    ('ADMIN', 'risk:read'), ('ADMIN', 'risk:update'),
    ('ADMIN', 'audit:read'), ('ADMIN', 'admin:read')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions(role_code, permission_code)
SELECT 'OWNER', code FROM permissions
ON CONFLICT DO NOTHING;

-- Every existing account receives the baseline role. Existing administrators
-- retain ADMIN privileges but are not silently elevated to OWNER.
INSERT INTO user_roles(user_id, role_code)
SELECT id, 'USER' FROM users
ON CONFLICT DO NOTHING;

INSERT INTO user_roles(user_id, role_code)
SELECT id, 'ADMIN' FROM users WHERE role = 'ADMIN'
ON CONFLICT DO NOTHING;

CREATE TABLE security_bootstrap_state (
    bootstrap_key VARCHAR(32) PRIMARY KEY,
    completed_at TIMESTAMPTZ,
    completed_user_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_security_bootstrap_user
        FOREIGN KEY (completed_user_id) REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT ck_security_bootstrap_completion
        CHECK ((completed_at IS NULL) = (completed_user_id IS NULL))
);

INSERT INTO security_bootstrap_state(bootstrap_key) VALUES ('INITIAL_OWNER')
ON CONFLICT DO NOTHING;

ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS request_id VARCHAR(100);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS ip_hash VARCHAR(64);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS device_id VARCHAR(128);

CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id
    ON audit_logs(request_id) WHERE request_id IS NOT NULL;

COMMENT ON TABLE audit_logs IS 'Append-oriented security and administration audit log; application exposes no update/delete API.';
COMMENT ON TABLE outbox_events IS 'Transactional outbox shared by security and domain events.';
