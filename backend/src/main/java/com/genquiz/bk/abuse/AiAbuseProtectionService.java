package com.genquiz.bk.abuse;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.job.Job;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;

@Service
public class AiAbuseProtectionService {
    private final AntiAbuseProperties properties;
    private final AbuseRequestIdentityService identities;
    private final AccountReputationService reputation;
    private final AtomicAbuseStore store;
    private final AiCostEstimator costs;
    private final ChallengeVerifier challenge;
    private final ObjectMapper mapper;
    private final Clock clock;

    @Autowired
    public AiAbuseProtectionService(AntiAbuseProperties properties,
                                    AbuseRequestIdentityService identities,
                                    AccountReputationService reputation,
                                    AtomicAbuseStore store,
                                    AiCostEstimator costs,
                                    ChallengeVerifier challenge,
                                    ObjectMapper mapper) {
        this(properties, identities, reputation, store, costs, challenge, mapper, Clock.systemUTC());
    }

    AiAbuseProtectionService(AntiAbuseProperties properties,
                             AbuseRequestIdentityService identities,
                             AccountReputationService reputation,
                             AtomicAbuseStore store, AiCostEstimator costs,
                             ChallengeVerifier challenge, ObjectMapper mapper, Clock clock) {
        this.properties = properties; this.identities = identities; this.reputation = reputation;
        this.store = store; this.costs = costs; this.challenge = challenge;
        this.mapper = mapper; this.clock = clock;
    }

    public AiAdmissionContext admit(UUID userId, String endpoint, String payload) {
        if (!properties.enabled()) return null;
        RiskAssessment assessment = reputation.assess(userId);
        if (assessment.serviceLevel() == ServiceLevel.BLOCKED) {
            throw denied(HttpStatus.FORBIDDEN, "RISK_RESTRICTED",
                    "Tài khoản hiện không được phép sử dụng chức năng AI tốn tài nguyên.");
        }
        AbuseRequestIdentity identity = identities.current();
        AccountReputationService.EffectiveAiPolicy effective = reputation.effectivePolicy(userId, assessment.serviceLevel());
        AntiAbuseProperties.LevelPolicy policy = effective == null
                ? properties.levels().forLevel(assessment.serviceLevel()) : effective.policy();
        if (policy.challengeRequired() && !challenge.verify(identity.challengeToken(), identity.ipHash())) {
            reputation.record(userId, RiskEventType.BOT_CHALLENGE_FAILED, RiskSeverity.MEDIUM,
                    0.10, Map.of("endpoint", endpoint));
            throw denied(HttpStatus.FORBIDDEN, "CHALLENGE_REQUIRED",
                    "Yêu cầu xác minh bổ sung trước khi sử dụng AI.");
        }
        RequestShape shape = shape(payload);
        BigDecimal estimate = costs.estimate(shape.model(), shape.questionCount());
        String leaseId = UUID.randomUUID().toString();
        AiAdmissionDecision decision;
        try {
            decision = store.admit(userId, leaseId, identity, endpoint, assessment.serviceLevel(),
                    policy, estimate, LocalDate.now(clock.withZone(ZoneOffset.UTC)));
        } catch (DataAccessException | IllegalStateException exception) {
            throw denied(HttpStatus.SERVICE_UNAVAILABLE, "ABUSE_PROTECTION_UNAVAILABLE",
                    "Không thể xác minh hạn mức AI lúc này. Vui lòng thử lại sau.");
        }
        if (decision != AiAdmissionDecision.ALLOWED) {
            RiskSeverity severity = decision == AiAdmissionDecision.COST_BUDGET
                    ? RiskSeverity.MEDIUM : RiskSeverity.LOW;
            reputation.record(userId, RiskEventType.RATE_LIMIT_TRIGGERED, severity,
                    decision == AiAdmissionDecision.COST_BUDGET ? 0.08 : 0.04,
                    Map.of("dimension", decision.name(), "endpoint", endpoint));
            throw rejection(decision);
        }
        AiAdmissionContext admission = new AiAdmissionContext(leaseId, identity.ipHash(), identity.deviceHash(),
                endpoint, shape.model(), estimate, true);
        registerRollbackRelease(userId, admission);
        return admission;
    }

    public AiAdmissionContext admitDirect(UUID userId, String endpoint, String model, int estimatedUnits) {
        String payload = "{\"model\":\"" + safeModel(model) + "\",\"questionCounts\":{\"singleChoice\":"
                + Math.max(1, estimatedUnits) + ",\"multipleSelect\":0,\"fillBlank\":0}}";
        return admit(userId, endpoint, payload);
    }

    public void completedDirect(UUID userId, AiAdmissionContext admission, String model,
                                Map<String, Integer> usage) {
        if (!properties.enabled() || admission == null) return;
        BigDecimal actual = costs.actual(model, usage);
        try {
            store.adjustActualCost(userId, LocalDate.now(clock.withZone(ZoneOffset.UTC)),
                    admission.estimatedCost(), actual, properties.costKeyTtl());
        } catch (RuntimeException ignored) { /* PostgreSQL reputation still records the usage. */ }
        reputation.recordAiUsage(userId, actual);
        reputation.recordLegitimateActivity(userId);
    }

    public void releaseDirect(UUID userId, AiAdmissionContext admission) {
        if (!properties.enabled() || admission == null || !admission.concurrencyReserved()) return;
        try { store.release(userId, admission.leaseId(), admission.ipHash(), admission.deviceHash()); }
        catch (RuntimeException ignored) { /* Redis TTL prevents permanent leakage. */ }
    }

    public void completed(Job job, String resultPayload) {
        if (!properties.enabled() || !job.isAiConcurrencyReserved()) return;
        BigDecimal actual = costs.actual(job.getAiModel(), usage(resultPayload));
        job.recordAiActualCost(actual);
        try {
            store.adjustActualCost(job.getSubjectUserId(), LocalDate.now(clock.withZone(ZoneOffset.UTC)),
                    job.getAiEstimatedCost(), actual, properties.costKeyTtl());
        } catch (RuntimeException ignored) {
            // Usage persistence remains authoritative; Redis has a bounded TTL and may recover independently.
        }
        reputation.recordAiUsage(job.getSubjectUserId(), actual);
        reputation.recordLegitimateActivity(job.getSubjectUserId());
        if (actual.compareTo(job.getAiEstimatedCost().multiply(BigDecimal.valueOf(2))) > 0) {
            reputation.record(job.getSubjectUserId(), RiskEventType.ABNORMAL_AI_USAGE,
                    RiskSeverity.MEDIUM, 0.08, Map.of("model", safeModel(job.getAiModel())));
        }
        release(job);
    }

    public void release(Job job) {
        if (!properties.enabled() || !job.isAiConcurrencyReserved()) return;
        try {
            store.release(job.getSubjectUserId(), job.getAiLeaseId(), job.getAiIpHash(), job.getAiDeviceHash());
        } catch (RuntimeException ignored) {
            // Concurrency keys always have a safety TTL.
        }
        job.clearAiAdmission();
    }

    private Map<String, Integer> usage(String resultPayload) {
        var values = new HashMap<String, Integer>();
        try {
            JsonNode usage = mapper.readTree(resultPayload == null ? "{}" : resultPayload).path("usage");
            if (usage.isObject()) {
                usage.properties().forEach(entry -> {
                    if (entry.getValue().isNumber()) values.put(entry.getKey(), entry.getValue().intValue());
                });
            }
        } catch (RuntimeException ignored) {
            return Map.of();
        }
        return values;
    }

    private RequestShape shape(String payload) {
        try {
            JsonNode root = mapper.readTree(payload == null ? "{}" : payload);
            JsonNode counts = root.path("questionCounts");
            int count = counts.path("singleChoice").intValue(0)
                    + counts.path("multipleSelect").intValue(0)
                    + counts.path("fillBlank").intValue(0);
            String model = root.path("model").stringValue("");
            if (model.isBlank()) model = "default";
            return new RequestShape(Math.max(1, count), safeModel(model));
        } catch (RuntimeException exception) {
            return new RequestShape(1, "default");
        }
    }

    private void registerRollbackRelease(UUID userId, AiAdmissionContext admission) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) return;
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCompletion(int status) {
                if (status == STATUS_ROLLED_BACK) {
                    try { store.release(userId, admission.leaseId(), admission.ipHash(), admission.deviceHash()); }
                    catch (RuntimeException ignored) { /* TTL is the final safety net. */ }
                }
            }
        });
    }

    private ApiException rejection(AiAdmissionDecision decision) {
        return switch (decision) {
            case USER_RATE_LIMIT, IP_RATE_LIMIT, DEVICE_RATE_LIMIT -> denied(HttpStatus.TOO_MANY_REQUESTS,
                    "RATE_LIMIT_EXCEEDED", "Bạn đã gửi quá nhiều yêu cầu AI. Vui lòng thử lại sau.");
            case DAILY_QUOTA -> denied(HttpStatus.TOO_MANY_REQUESTS, "AI_QUOTA_EXCEEDED",
                    "Bạn đã sử dụng hết hạn mức AI hôm nay.");
            case COST_BUDGET -> denied(HttpStatus.TOO_MANY_REQUESTS, "AI_COST_BUDGET_EXCEEDED",
                    "Ngân sách sử dụng AI hôm nay đã đạt giới hạn.");
            case USER_CONCURRENCY, IP_CONCURRENCY, DEVICE_CONCURRENCY -> denied(HttpStatus.TOO_MANY_REQUESTS,
                    "AI_CONCURRENCY_LIMIT", "Đã có quá nhiều tác vụ AI đang xử lý.");
            case ALLOWED -> throw new IllegalArgumentException("Không thể từ chối quyết định ALLOWED.");
        };
    }

    private static ApiException denied(HttpStatus status, String code, String message) {
        return new ApiException(status, code, message);
    }

    private static String safeModel(String model) {
        if (model == null || model.isBlank()) return "default";
        String safe = model.replaceAll("[^a-zA-Z0-9._:-]", "_");
        return safe.substring(0, Math.min(120, safe.length()));
    }

    private record RequestShape(int questionCount, String model) {}
}
