package com.genquiz.bk.abuse;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

@Component
public class RedisAtomicAbuseStore implements AtomicAbuseStore {
    private static final DefaultRedisScript<Long> ADMIT = new DefaultRedisScript<>("""
            local vals = {}
            for i=1,5 do vals[i] = tonumber(redis.call('GET', KEYS[i]) or '0') end
            for i=6,8 do
              redis.call('ZREMRANGEBYSCORE', KEYS[i], '-inf', ARGV[11])
              vals[i] = redis.call('ZCARD', KEYS[i])
            end
            if vals[1] >= tonumber(ARGV[1]) then return 1 end
            if vals[2] >= tonumber(ARGV[2]) then return 2 end
            if vals[3] >= tonumber(ARGV[3]) then return 3 end
            if vals[4] >= tonumber(ARGV[4]) then return 4 end
            if vals[5] + tonumber(ARGV[5]) > tonumber(ARGV[6]) then return 5 end
            if vals[6] >= tonumber(ARGV[7]) then return 6 end
            if vals[7] >= tonumber(ARGV[7]) then return 7 end
            if vals[8] >= tonumber(ARGV[7]) then return 8 end
            for i=1,3 do redis.call('INCR', KEYS[i]); redis.call('PEXPIRE', KEYS[i], ARGV[8]) end
            redis.call('INCR', KEYS[4]); redis.call('PEXPIRE', KEYS[4], ARGV[9])
            redis.call('INCRBY', KEYS[5], ARGV[5]); redis.call('PEXPIRE', KEYS[5], ARGV[9])
            local expiresAt = tonumber(ARGV[11]) + tonumber(ARGV[10])
            for i=6,8 do
              redis.call('ZADD', KEYS[i], expiresAt, ARGV[12])
              redis.call('PEXPIRE', KEYS[i], ARGV[10])
            end
            return 0
            """, Long.class);
    private static final DefaultRedisScript<Long> RELEASE = new DefaultRedisScript<>("""
            for i=1,3 do redis.call('ZREM', KEYS[i], ARGV[1]) end
            return 1
            """, Long.class);
    private static final DefaultRedisScript<Long> ADJUST_COST = new DefaultRedisScript<>("""
            local current = tonumber(redis.call('GET', KEYS[1]) or '0')
            local next = current + tonumber(ARGV[1])
            if next < 0 then next = 0 end
            redis.call('SET', KEYS[1], tostring(next), 'PX', ARGV[2])
            return next
            """, Long.class);

    private final StringRedisTemplate redis;
    private final AntiAbuseProperties properties;

    public RedisAtomicAbuseStore(StringRedisTemplate redis, AntiAbuseProperties properties) {
        this.redis = redis; this.properties = properties;
    }

    @Override
    public AiAdmissionDecision admit(UUID userId, String leaseId, AbuseRequestIdentity identity, String endpoint,
                                     ServiceLevel level, AntiAbuseProperties.LevelPolicy policy,
                                     BigDecimal estimatedCost, LocalDate date) {
        String safeEndpoint = endpoint.replaceAll("[^a-zA-Z0-9:_-]", "_");
        List<String> keys = List.of(
                "rl:user:" + userId + ":" + safeEndpoint,
                "rl:ip:" + identity.ipHash() + ":" + safeEndpoint,
                "rl:device:" + identity.deviceHash() + ":" + safeEndpoint,
                "quota:user:" + userId + ":ai:" + date,
                "cost:user:" + userId + ":ai:" + date,
                "concurrent:user:" + userId + ":ai",
                "concurrent:ip:" + identity.ipHash() + ":ai",
                "concurrent:device:" + identity.deviceHash() + ":ai");
        Long result = redis.execute(ADMIT, keys,
                Integer.toString(properties.userRateLimit()),
                Integer.toString(properties.ipRateLimit()),
                Integer.toString(properties.deviceRateLimit()),
                Integer.toString(policy.dailyQuota()),
                Long.toString(micros(estimatedCost)),
                Long.toString(micros(policy.dailyCostBudget())),
                Integer.toString(policy.concurrency()),
                Long.toString(properties.rateWindow().toMillis()),
                Long.toString(properties.costKeyTtl().toMillis()),
                Long.toString(properties.concurrencyTtl().toMillis()),
                Long.toString(System.currentTimeMillis()),
                leaseId);
        int code = result == null ? -1 : result.intValue();
        return switch (code) {
            case 0 -> AiAdmissionDecision.ALLOWED;
            case 1 -> AiAdmissionDecision.USER_RATE_LIMIT;
            case 2 -> AiAdmissionDecision.IP_RATE_LIMIT;
            case 3 -> AiAdmissionDecision.DEVICE_RATE_LIMIT;
            case 4 -> AiAdmissionDecision.DAILY_QUOTA;
            case 5 -> AiAdmissionDecision.COST_BUDGET;
            case 6 -> AiAdmissionDecision.USER_CONCURRENCY;
            case 7 -> AiAdmissionDecision.IP_CONCURRENCY;
            case 8 -> AiAdmissionDecision.DEVICE_CONCURRENCY;
            default -> throw new IllegalStateException("Redis không trả kết quả anti-abuse hợp lệ.");
        };
    }

    @Override
    public void release(UUID userId, String leaseId, String ipHash, String deviceHash) {
        redis.execute(RELEASE, List.of(
                "concurrent:user:" + userId + ":ai",
                "concurrent:ip:" + ipHash + ":ai",
                "concurrent:device:" + deviceHash + ":ai"), leaseId);
    }

    @Override
    public void adjustActualCost(UUID userId, LocalDate date, BigDecimal estimated,
                                 BigDecimal actual, java.time.Duration ttl) {
        long delta = micros(actual) - micros(estimated);
        redis.execute(ADJUST_COST, List.of("cost:user:" + userId + ":ai:" + date),
                Long.toString(delta), Long.toString(ttl.toMillis()));
    }

    private static long micros(BigDecimal value) {
        return value.max(BigDecimal.ZERO).multiply(BigDecimal.valueOf(1_000_000))
                .setScale(0, RoundingMode.CEILING).longValueExact();
    }
}
