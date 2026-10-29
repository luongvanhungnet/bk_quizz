package com.genquiz.bk.abuse;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;

class RedisAtomicAbuseStoreTest {
    @SuppressWarnings({"unchecked", "rawtypes"})
    @Test
    void usesEndpointSpecificUserIpDeviceQuotaCostAndConcurrencyKeysAtomically() {
        StringRedisTemplate redis = mock(StringRedisTemplate.class);
        when(redis.execute(any(RedisScript.class), anyList(),
                anyString(), anyString(), anyString(), anyString(), anyString(),
                anyString(), anyString(), anyString(), anyString(), anyString(),
                anyString(), anyString())).thenReturn(0L);
        var store = new RedisAtomicAbuseStore(redis, AntiAbuseTestProperties.enabled());
        UUID userId = UUID.randomUUID();

        AiAdmissionDecision result = store.admit(userId, "lease-1",
                new AbuseRequestIdentity("iphash", "devicehash", null), "quiz:generation",
                ServiceLevel.NORMAL, AntiAbuseTestProperties.enabled().levels().normal(),
                new BigDecimal("0.01"), LocalDate.of(2026, 9, 4));

        assertThat(result).isEqualTo(AiAdmissionDecision.ALLOWED);
        ArgumentCaptor<List<String>> keys = ArgumentCaptor.forClass(List.class);
        org.mockito.Mockito.verify(redis).execute(any(RedisScript.class), keys.capture(),
                anyString(), anyString(), anyString(), anyString(), anyString(),
                anyString(), anyString(), anyString(), anyString(), anyString(),
                anyString(), anyString());
        assertThat(keys.getValue()).containsExactly(
                "rl:user:" + userId + ":quiz:generation",
                "rl:ip:iphash:quiz:generation",
                "rl:device:devicehash:quiz:generation",
                "quota:user:" + userId + ":ai:2026-09-04",
                "cost:user:" + userId + ":ai:2026-09-04",
                "concurrent:user:" + userId + ":ai",
                "concurrent:ip:iphash:ai",
                "concurrent:device:devicehash:ai");
    }
}
