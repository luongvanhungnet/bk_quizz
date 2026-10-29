# Anti-abuse and account reputation

## Scope

BKQuiz protects the two expensive AI paths before calling RAG/provider services:

- Quiz generation jobs (`quiz_generation` and `quiz_generation_retry`).
- Attempt result tutor chat (`attempt_ai_chat`).

Cheap endpoints retain the existing bounded in-process limiter. That path is deliberately limited fail-open during a Redis incident; expensive AI is fail-closed with `503 ABUSE_PROTECTION_UNAVAILABLE` because quota and monetary cost cannot be verified safely.

## Request identity and privacy

The server derives request dimensions from the authenticated user, the first trusted application-facing address in `X-Forwarded-For`, and `X-Device-Id`. If the device header is absent, a bounded user-agent/address-derived value is used. IP and device values are HMAC-SHA-256 hashed with `ANTI_ABUSE_IP_HASH_SECRET` before use. Raw IPs, authorization headers, JWTs, refresh tokens, passwords, provider keys, and challenge secrets are not stored in risk metadata.

Clients may send a Turnstile result in `X-Turnstile-Token`. The token is never trusted by itself; the backend verifies it against Cloudflare when the resolved service level requires a challenge.

## Redis structures and atomic admission

The admission Lua script evaluates and mutates all required dimensions as one Redis operation:

| Key | Type | Purpose |
|---|---|---|
| `rl:user:{userId}:{endpoint}` | string counter | Per-user, endpoint-specific rate window |
| `rl:ip:{ipHash}:{endpoint}` | string counter | Per-IP-hash, endpoint-specific rate window |
| `rl:device:{deviceHash}:{endpoint}` | string counter | Per-device-hash, endpoint-specific rate window |
| `quota:user:{userId}:ai:{UTC-date}` | string counter | Daily accepted AI operations |
| `cost:user:{userId}:ai:{UTC-date}` | integer micro-units | Estimated daily monetary cost, later reconciled with actual usage |
| `concurrent:user:{userId}:ai` | sorted set | Active AI lease tokens by user |
| `concurrent:ip:{ipHash}:ai` | sorted set | Active AI lease tokens by IP hash |
| `concurrent:device:{deviceHash}:ai` | sorted set | Active AI lease tokens by device hash |

Concurrency sorted-set scores are lease expiry times in epoch milliseconds and members are unique request lease IDs. Admission first deletes expired members and checks `ZCARD`; release removes only its own member. This prevents a late completion from releasing a newer request's slot. Key TTL remains a crash safety net.

No critical quota path uses a `GET -> calculate -> SET` sequence outside Redis. Actual cost reconciliation uses a second Lua script and never lets the daily value become negative.

## Admission and error behavior

The ordered checks are account service level/challenge, user/IP/device rate, daily quota, estimated cost budget, and user/IP/device concurrency. A rejected request never reaches the expensive provider.

Public error codes are:

- `RATE_LIMIT_EXCEEDED` (429)
- `AI_QUOTA_EXCEEDED` (429)
- `AI_COST_BUDGET_EXCEEDED` (429)
- `AI_CONCURRENCY_LIMIT` (429)
- `RISK_RESTRICTED` (403)
- `CHALLENGE_REQUIRED` (403)
- `ABUSE_PROTECTION_UNAVAILABLE` (503)

Quiz jobs persist their privacy-safe admission lease so success, terminal failure, transaction rollback, downstream exception, and administrator cancellation can release it. Streaming tutor chat releases in a `finally` block; Redis TTL covers process crashes.

## Cost control

`AiCostEstimator` separates pricing from admission business logic. The current configurable implementation estimates input/output tokens per generated question using configurable default per-million-token prices. Provider/model-specific pricing can replace or decorate this implementation later.

At admission, estimated cost is atomically reserved. On successful completion, reported input/output token usage is converted to actual estimated cost and the Redis daily total is adjusted by the difference. PostgreSQL reputation counters retain cumulative completed operation/cost telemetry. A request can therefore be rejected for monetary budget even while its count quota remains.

## Reputation and progressive quota

PostgreSQL tables introduced by Flyway V27 are:

- `risk_events`: append-only typed signals with bounded delta, severity, safe JSON metadata, and timestamp.
- `account_reputations`: latest explainable score/service level plus legitimate activity, successful session, AI operation, and cumulative AI cost counters.

The rule-based calculation starts new accounts at low trust. Positive contributions include verified email, normal completed AI activity, successful sessions, and a capped account-age contribution. Account age alone can never produce `TRUSTED`: verified email, the configured minimum score, and the configured minimum legitimate activity count are all required. Positive risk deltas from the latest 30 days reduce trust and resolve service level thresholds.

Service levels influence policy as follows:

| Level | Default behavior |
|---|---|
| `TRUSTED` | Higher daily quota/budget and concurrency |
| `NORMAL` | Standard quota/budget and concurrency |
| `CAUTION` | New/unproven account; reduced quota and one concurrent operation |
| `RESTRICTED` | Minimal quota/budget, one concurrent operation, server-verified challenge required |
| `BLOCKED` | Expensive AI denied |

One weak event does not automatically ban an account; service level follows the configurable aggregate thresholds. Failed known-user logins and refresh-token reuse create risk events. Successful logins and legitimate completed AI activity improve reputation.

Administrators holding `risk:read` can call `GET /api/admin/users/{userId}/risk`. Normal users cannot access this model. The response exposes high-level contributions, not raw identifiers, Redis keys, thresholds, or enforcement internals.

## Configuration

Production should store `REDIS_URL`, `ANTI_ABUSE_IP_HASH_SECRET`, and `TURNSTILE_SECRET_KEY` in a secret manager.

Core switches and timeouts:

- `ANTI_ABUSE_ENABLED` (production default via profile: `true`)
- `REDIS_URL`, `REDIS_CONNECT_TIMEOUT`, `REDIS_COMMAND_TIMEOUT`
- `ANTI_ABUSE_IP_HASH_SECRET`
- `ANTI_ABUSE_RATE_WINDOW`, `ANTI_ABUSE_USER_RATE_LIMIT`, `ANTI_ABUSE_IP_RATE_LIMIT`, `ANTI_ABUSE_DEVICE_RATE_LIMIT`
- `AI_CONCURRENCY_TTL`, `AI_COST_KEY_TTL`

Pricing:

- `AI_DEFAULT_INPUT_COST_PER_MILLION`, `AI_DEFAULT_OUTPUT_COST_PER_MILLION`
- `AI_ESTIMATED_INPUT_TOKENS_PER_QUESTION`, `AI_ESTIMATED_OUTPUT_TOKENS_PER_QUESTION`

Level policy:

- `AI_{TRUSTED|NORMAL|CAUTION|RESTRICTED}_DAILY_QUOTA`
- `AI_{TRUSTED|NORMAL|CAUTION|RESTRICTED}_DAILY_COST_BUDGET`
- `AI_{TRUSTED|NORMAL|CAUTION|RESTRICTED}_CONCURRENCY`

Risk rules:

- `RISK_VERIFIED_EMAIL_TRUST`, `RISK_NORMAL_ACTIVITY_TRUST`, `RISK_SUCCESSFUL_SESSION_TRUST`
- `RISK_ACCOUNT_AGE_TRUST_PER_DAY`, `RISK_ACCOUNT_AGE_TRUST_CAP`
- `RISK_TRUSTED_MIN_SCORE`, `RISK_TRUSTED_MIN_LEGITIMATE_ACTIVITIES`
- `RISK_CAUTION_SCORE`, `RISK_RESTRICTED_SCORE`, `RISK_BLOCKED_SCORE`

Challenge:

- `TURNSTILE_ENABLED`, `TURNSTILE_SECRET_KEY`, `TURNSTILE_VERIFY_URL`

## Verification

From `backend`:

```powershell
.\mvnw.cmd -Dtest="com.genquiz.bk.abuse.*Test" test
.\mvnw.cmd verify
```

Flyway integration tests migrate a clean PostgreSQL database through V27. Unit tests cover all rate dimensions, endpoint keying, quota, cost, concurrency, release after failure, Redis fail-closed behavior, progressive trust, repeated risk, BLOCKED denial, and risk endpoint authorization.

## Remaining extensions

- Add a dedicated multi-account/device correlation detector; the schema and event type are ready, but automatic cross-account correlation is intentionally not inferred from one weak device signal.
- Add provider/model-specific price tables when contractual production prices are finalized.
- Add the frontend Turnstile widget/token lifecycle before enabling `TURNSTILE_ENABLED`; server verification is already present.
- Add retention/anonymization jobs for old risk events after the product retention period is approved.
