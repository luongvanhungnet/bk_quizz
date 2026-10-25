# BKQuiz administrative security architecture

## Scope and compatibility

BKQuiz keeps the existing access/refresh JWT flow, refresh cookie, XSRF filter,
`users` table and `users.role` account-type field. `users.role` remains the
compatibility value used by the current STUDENT/TEACHER UI; it is not the
source of administrative authorization.

Administrative authorization is database-backed RBAC:

- `roles`
- `permissions`
- `user_roles`
- `role_permissions`

Every account receives `USER`. A user may additionally receive SUPPORT,
ANALYST, MODERATOR, ADMIN or OWNER. The JWT contains a diagnostic snapshot of
roles and permissions, but `JwtAuthenticationFilter` reloads the current RBAC
snapshot from PostgreSQL for every authenticated request. Stale or forged
client claims therefore cannot grant authority.

## Authentication flow

1. Public registration accepts only STUDENT/TEACHER account type and inserts
   the baseline RBAC role USER in the same transaction.
2. Password login creates an access token and rotating refresh session.
3. The refresh token remains an HttpOnly cookie and the existing XSRF cookie
   and header behavior is unchanged.
4. Successful/failed login, admin login and password reset are audited without
   storing passwords, JWTs, refresh tokens or Authorization headers.
5. Role changes revoke all refresh sessions for the target user. Access-token
   privileges disappear immediately because authorities are reloaded from the
   database on each request.

## Role-to-permission policy

| Role | Administrative permissions |
|---|---|
| USER | none |
| SUPPORT | `user:read` |
| ANALYST | `analytics:read` |
| MODERATOR | `user:read`, `user:suspend`, `user:ban`, `risk:read` |
| ADMIN | analytics, user, quota, risk and audit operational permissions plus `admin:read` |
| OWNER | every administrative permission, including `admin:grant`, `admin:revoke`, `system:config` |

Controllers use method authorization such as
`@PreAuthorize("hasAuthority('admin:grant')")`. Privilege-escalation rules are
also enforced inside `AdminRoleService`.

## Initial OWNER bootstrap

Bootstrap never creates an account and accepts no password. First register a
normal account, verify its email and copy its PostgreSQL UUID. Run Flyway V26,
then create one Cloud Run revision with:

```text
ADMIN_BOOTSTRAP_ENABLED=true
ADMIN_BOOTSTRAP_USER_ID=<verified-active-user-uuid>
```

The runner obtains a PostgreSQL advisory transaction lock, locks the
`security_bootstrap_state` row, verifies the target and inserts OWNER. It then
persists completion, audit and outbox records. Restarts and concurrent Cloud
Run instances cannot execute it again. If an OWNER already exists, bootstrap
is permanently closed without creating another.

After the successful revision, deploy another revision with:

```text
ADMIN_BOOTSTRAP_ENABLED=false
```

Do not use or recreate `ADMIN_BOOTSTRAP_PASSWORD`, `ADMIN_BOOTSTRAP_EMAIL` or
`ADMIN_BOOTSTRAP_USERNAME`. No bootstrap HTTP endpoint exists.

For local development, use a disposable database, register/verify a user,
enable bootstrap for one startup, then disable it. Production and staging must
use different databases and different target user IDs.

`ADMIN_BOOTSTRAP_USER_ID` is an identifier rather than a credential and may be
an environment variable. JWT signing keys, database credentials, Resend keys
and other secrets remain Google Secret Manager bindings; never place them in
deployment YAML or Git.

## Administrative role APIs

- `GET /api/admin/users/{userId}/roles` — requires `admin:read`.
- `POST /api/admin/users/{userId}/roles/{role}` — requires `admin:grant`.
- `DELETE /api/admin/users/{userId}/roles/{role}` — requires `admin:revoke`.

Only an actual OWNER passes the service-level grant/revoke guard. The normal
API cannot grant or revoke OWNER, cannot mutate the actor's own privileges and
cannot grant a privileged role to an inactive or unverified account. ADMIN
does not possess grant/revoke permissions.

## Audit and outbox

The existing append-oriented `audit_logs` table is reused and extended with
request ID, salted IP hash and bounded device ID. The application exposes only
read APIs for audit data. Metadata is restricted to safe identifiers, role
names and reason codes.

The existing `outbox_events` table is reused. OWNER bootstrap, role changes and
password changes insert an outbox event in the same PostgreSQL transaction as
the business mutation. `dedup_key` is unique. A future publisher can claim
PENDING/RETRY rows using `FOR UPDATE SKIP LOCKED`; Kafka is not required.

## Deployment order

1. Back up Neon and run Flyway V26 once through the migration job/direct Neon
   endpoint.
2. Deploy backend code with bootstrap disabled.
3. Verify existing ADMIN accounts received ADMIN and every user received USER.
4. If no OWNER exists, run the one-time bootstrap revision described above.
5. Disable bootstrap and test OWNER/ADMIN permissions and audit records.

Rollback application code is safe only while retaining the V26 tables. Do not
drop RBAC, audit or outbox data during rollback.

## Security assumptions and remaining work

- PostgreSQL is authoritative for current permissions.
- Database administrator access and Cloud Run deployment access are privileged
  operational controls outside this API.
- Normal administrative APIs intentionally cannot create another OWNER.
- Audit retention, export/SIEM delivery and an outbox publisher are operational
  follow-ups; audit update/delete endpoints must not be added.
