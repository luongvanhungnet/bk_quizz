package com.genquiz.bk.abuse;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.sql.Timestamp;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Service
public class AccountReputationService {
    private final JdbcTemplate jdbc;
    private final UserRepository users;
    private final ObjectMapper mapper;
    private final AntiAbuseProperties properties;
    private final Clock clock;

    @Autowired
    public AccountReputationService(JdbcTemplate jdbc, UserRepository users, ObjectMapper mapper,
                                    AntiAbuseProperties properties) {
        this(jdbc, users, mapper, properties, Clock.systemUTC());
    }

    AccountReputationService(JdbcTemplate jdbc, UserRepository users, ObjectMapper mapper,
                             AntiAbuseProperties properties, Clock clock) {
        this.jdbc = jdbc; this.users = users; this.mapper = mapper;
        this.properties = properties; this.clock = clock;
    }

    @Transactional
    public RiskAssessment assess(UUID userId) {
        User user = users.findByIdAndDeletedAtIsNull(userId).orElseThrow(() ->
                new ApiException(HttpStatus.NOT_FOUND, "USER_NOT_FOUND", "Không tìm thấy tài khoản."));
        jdbc.update("insert into account_reputations(user_id) values (?) on conflict (user_id) do nothing", userId);
        Map<String, Object> row = jdbc.queryForMap("""
                select legitimate_activity_count, successful_session_count, service_level_override,
                       daily_quota_override, daily_cost_budget_override
                from account_reputations where user_id=?
                """, userId);
        int legitimate = ((Number) row.get("legitimate_activity_count")).intValue();
        int sessions = ((Number) row.get("successful_session_count")).intValue();
        BigDecimal risk = jdbc.queryForObject("""
                select coalesce(sum(greatest(risk_delta, 0)), 0)
                from risk_events where user_id=? and created_at >= ?
                """, BigDecimal.class, userId,
                Timestamp.from(Instant.now(clock).minus(Duration.ofDays(30))));
        double riskScore = clamp(risk == null ? 0 : risk.doubleValue(), 0, 1);

        var signals = new ArrayList<RiskAssessment.Signal>();
        int trust = 20;
        if (user.isEmailVerified()) {
            trust += properties.risk().verifiedEmailTrust();
            signals.add(new RiskAssessment.Signal("EMAIL_VERIFIED",
                    -properties.risk().verifiedEmailTrust() / 100.0));
        }
        int activityTrust = Math.min(30, legitimate * properties.risk().normalActivityTrust());
        if (activityTrust > 0) signals.add(new RiskAssessment.Signal("LEGITIMATE_ACTIVITY", -activityTrust / 100.0));
        trust += activityTrust;
        int sessionTrust = Math.min(15, sessions * properties.risk().successfulSessionTrust());
        if (sessionTrust > 0) signals.add(new RiskAssessment.Signal("SUCCESSFUL_SESSIONS", -sessionTrust / 100.0));
        trust += sessionTrust;
        long ageDays = user.getCreatedAt() == null ? 0
                : Math.max(0, Duration.between(user.getCreatedAt(), Instant.now(clock)).toDays());
        int ageTrust = Math.min(properties.risk().accountAgeTrustCap(),
                properties.risk().accountAgeTrustPerDay().multiply(BigDecimal.valueOf(ageDays)).intValue());
        if (ageTrust > 0) signals.add(new RiskAssessment.Signal("ACCOUNT_AGE", -ageTrust / 100.0));
        trust += ageTrust;
        if (riskScore > 0) signals.add(new RiskAssessment.Signal("RECENT_RISK_EVENTS", riskScore));
        trust = (int) clamp(trust - Math.round(riskScore * 60), 0, 100);

        String override = (String) row.get("service_level_override");
        ServiceLevel level = override == null ? resolveLevel(user, trust, riskScore, legitimate)
                : ServiceLevel.valueOf(override);
        jdbc.update("""
                update account_reputations set trust_score=?, risk_score=?, service_level=?,
                last_calculated_at=?, version=version+1 where user_id=?
                """, trust, BigDecimal.valueOf(riskScore).setScale(5, RoundingMode.HALF_UP),
                level.name(), Timestamp.from(Instant.now(clock)), userId);
        return new RiskAssessment(trust, riskScore, level, List.copyOf(signals));
    }

    @Transactional(readOnly = true)
    public EffectiveAiPolicy effectivePolicy(UUID userId, ServiceLevel level) {
        AntiAbuseProperties.LevelPolicy base = properties.levels().forLevel(level);
        List<Map<String,Object>> rows = jdbc.queryForList("""
                select daily_quota_override,daily_cost_budget_override
                from account_reputations where user_id=?
                """, userId);
        if (rows.isEmpty()) return new EffectiveAiPolicy(base, false);
        Map<String,Object> row=rows.get(0);
        Integer quota=row.get("daily_quota_override") instanceof Number n?n.intValue():null;
        BigDecimal budget=row.get("daily_cost_budget_override") instanceof BigDecimal b?b:null;
        return new EffectiveAiPolicy(new AntiAbuseProperties.LevelPolicy(
                quota==null?base.dailyQuota():quota,
                budget==null?base.dailyCostBudget():budget,
                base.concurrency(),base.challengeRequired()), quota!=null||budget!=null);
    }

    public record EffectiveAiPolicy(AntiAbuseProperties.LevelPolicy policy, boolean overridden) {}

    @Transactional
    public void record(UUID userId, RiskEventType type, RiskSeverity severity,
                       double delta, Map<String, ?> metadata) {
        try {
            jdbc.update("""
                    insert into risk_events(id,user_id,event_type,severity,risk_delta,metadata)
                    values (?,?,?,?,?,cast(? as jsonb))
                    """, UUID.randomUUID(), userId, type.name(), severity.name(),
                    BigDecimal.valueOf(clamp(delta, -1, 1)), mapper.writeValueAsString(metadata == null ? Map.of() : metadata));
        } catch (JacksonException exception) {
            throw new IllegalArgumentException("Không thể ghi nhận risk event.", exception);
        }
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordIndependent(UUID userId, RiskEventType type, RiskSeverity severity,
                                  double delta, Map<String, ?> metadata) {
        record(userId, type, severity, delta, metadata);
    }

    @Transactional
    public void recordLegitimateActivity(UUID userId) {
        jdbc.update("insert into account_reputations(user_id) values (?) on conflict (user_id) do nothing", userId);
        jdbc.update("update account_reputations set legitimate_activity_count=legitimate_activity_count+1 where user_id=?", userId);
    }

    @Transactional
    public void recordSuccessfulSession(UUID userId) {
        jdbc.update("insert into account_reputations(user_id) values (?) on conflict (user_id) do nothing", userId);
        jdbc.update("update account_reputations set successful_session_count=successful_session_count+1 where user_id=?", userId);
    }

    @Transactional
    public void recordAiUsage(UUID userId, BigDecimal cost) {
        jdbc.update("insert into account_reputations(user_id) values (?) on conflict (user_id) do nothing", userId);
        jdbc.update("""
                update account_reputations set ai_operation_count=ai_operation_count+1,
                ai_cost_total=ai_cost_total+? where user_id=?
                """, cost.max(BigDecimal.ZERO), userId);
    }

    private ServiceLevel resolveLevel(User user, int trust, double risk, int legitimate) {
        if (risk >= properties.risk().blockedRiskScore().doubleValue()) return ServiceLevel.BLOCKED;
        if (risk >= properties.risk().restrictedRiskScore().doubleValue()) return ServiceLevel.RESTRICTED;
        if (risk >= properties.risk().cautionRiskScore().doubleValue()) return ServiceLevel.CAUTION;
        if (user.isEmailVerified()
                && legitimate >= properties.risk().trustedMinLegitimateActivities()
                && trust >= properties.risk().trustedMinScore()) return ServiceLevel.TRUSTED;
        if (user.isEmailVerified() && legitimate >= 2) return ServiceLevel.NORMAL;
        return ServiceLevel.CAUTION;
    }

    private static double clamp(double value, double min, double max) {
        return Math.max(min, Math.min(max, value));
    }
}
