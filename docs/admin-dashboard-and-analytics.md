# BKQuiz administrative dashboard and analytics

## Scope and architecture

The implementation deliberately uses the existing PostgreSQL, Spring Boot, Redis and React stack. It does not add ClickHouse or another event platform. Domain writes append a small, non-sensitive row to `product_events` in the same PostgreSQL transaction through database triggers. Dashboard requests read idempotent UTC daily projections rather than repeatedly scanning domain tables.

```text
domain transaction -> product_events -> scheduled/replayable aggregation
                                      -> daily_platform_metrics
                                      -> daily_user_metrics
                                      -> daily_ai_metrics
                                      -> daily_security_metrics
                                      -> permission-protected admin APIs -> React/ECharts
```

The event payload contains resource identifiers, status, model and cost fields only. It must never contain prompts, document text, answers, passwords, tokens, provider keys or credentials. Existing security mutations also continue to use the transactional outbox and immutable `audit_logs`.

## Product events

V28 records `USER_REGISTERED`, `USER_ACTIVATED`, `DOCUMENT_UPLOADED`, `DOCUMENT_INGESTED`, `QUIZ_CREATED`, `AI_QUIZ_GENERATED`, `AI_REQUEST_COMPLETED`, `QUESTION_ANSWERED`, `QUIZ_COMPLETED`, `CLASS_CREATED`, `CLASS_JOINED`, `AI_QUOTA_EXHAUSTED` and a bounded `SECURITY_EVENT` envelope.

`UPGRADE_CLICKED` and `SUBSCRIPTION_STARTED` are reserved event names but are not emitted because BKQuiz has no payment/subscription domain yet. The conversion metric explicitly returns `available=false` and `SUBSCRIPTION_DATA_NOT_AVAILABLE`; it never returns invented zero conversion.

## Aggregation

`AnalyticsAggregationService.recompute(from,to)` deletes and rebuilds only the requested date range in one transaction. Repeating it produces the same projection. The scheduled runner rebuilds today and yesterday because late job completion is possible.

Configuration:

- `ANALYTICS_AGGREGATION_ENABLED` (default `true`)
- `ANALYTICS_AGGREGATION_DELAY` (default `5m`)
- `ANALYTICS_MAX_RANGE_DAYS` (default `366`)

For multi-instance Cloud Run deployments, enable the scheduler on only one worker instance or call the recompute API from a single scheduler. Concurrent recomputations remain transactionally safe, but a single scheduler avoids redundant work.

## Metric definitions

- DAU: distinct users with at least one product event on the selected UTC day (registration-only events are excluded from the daily active count).
- WAU/MAU: distinct active users in the inclusive trailing 7/30 UTC days ending at `dateTo`.
- AI cost per active user: actual AI cost divided by active users; zero when the denominator is zero.
- AI cost per generated quiz: actual AI cost divided by successful generated quizzes.
- Failure rate: failed AI requests divided by completed AI requests.
- Quota rejection rate: quota/rate rejections divided by completed plus rejected AI requests.
- Top 1% AI cost share: sort users by positive AI cost descending, take `ceil(userCount * 0.01)` (at least one user), then divide their summed cost by total cost.

Retention uses exact-day cohort retention. A user belongs to cohort date C when `USER_REGISTERED` occurred on C. Dn retention is the number of that cohort with qualifying activity exactly on `C + n days`, divided by cohort size. The API reports D1, D7 and D30 separately and excludes cohorts too recent to observe.

## APIs and permissions

| API | Permission |
| --- | --- |
| `GET /api/admin/analytics/overview` | `analytics:read` |
| `GET /api/admin/analytics/users` | `analytics:read` |
| `GET /api/admin/analytics/ai` | `analytics:read` |
| `GET /api/admin/analytics/security` | `risk:read` |
| `POST /api/admin/analytics/recompute` | `system:config` (OWNER) |
| `GET /api/admin/users/{id}/investigation` | `user:read` and `risk:read` |
| `PATCH /api/admin/users/{id}/quota` | `quota:update` |
| `POST /api/admin/users/{id}/ban` | `user:ban` |
| `POST /api/admin/users/{id}/restore` | `user:ban` |
| `GET /api/admin/audit-events` | `audit:read` |

Analytics endpoints accept `dateFrom` and `dateTo` (`YYYY-MM-DD`) and reject ranges beyond the configured maximum. AI top users are capped at 100. Audit events accept date, event, actor and target filters with page sizes capped at 100. Investigation histories are capped at 50 rows per source. No endpoint returns password hashes, refresh sessions, access tokens, secrets or raw AI prompts.

SUPPORT remains user-read only. ANALYST can read business analytics but cannot mutate accounts. MODERATOR can use only its existing user/risk actions. ADMIN can investigate, suspend/ban, adjust quota and read audit according to V26 permissions, but cannot grant ADMIN/OWNER. OWNER retains protected role and recompute capabilities. UI route checks token permissions for navigation convenience; Spring method authorization is authoritative.

## Admin frontend

The existing `/admin` route now contains Overview, Users/User Investigation, AI Usage, Security/Abuse, Content, Files, Jobs and Audit tabs. Apache ECharts renders time series and distributions. Audit is read-only. The access token is decoded only to show permitted navigation; it remains stored in memory and server authorization is still required.

## Technical observability

`micrometer-registry-prometheus` activates `/actuator/prometheus` alongside existing Actuator HTTP, JVM, datasource, cache and Spring AI observations. Protect this endpoint at the platform/network layer in production. Metrics must use bounded tags (provider/model/error code), never user IDs, emails, prompts or document contents. Business dashboards use PostgreSQL projections and are intentionally separate from Prometheus/Grafana.

## Operations

Run migrations and tests:

```powershell
cd D:\BKQuiz\backend
.\mvnw.cmd verify

cd D:\BKQuiz\frontend
npm test
npm run typecheck
npm run lint
npm run build
```

Recompute a corrected range as OWNER:

```http
POST /api/admin/analytics/recompute?dateFrom=2026-09-01&dateTo=2026-09-05
Authorization: Bearer <owner access token>
```

V28 begins tracking from deployment time. Historical domain activity is not fabricated. If historical reporting is required, implement a reviewed one-time backfill that derives only facts available in immutable domain timestamps.

## Remaining work

- Provider-level latency is available through Spring AI observations where calls use Spring AI; the custom RAG HTTP client still needs a dedicated timer if per-provider latency is required in Grafana.
- Redis/outbox failure counters should be added when an alerting rule and scrape deployment are finalized.
- Subscription conversion stays unavailable until a real subscription/payment model exists.
- Product event retention/partitioning should be introduced only after observed volume justifies it.
