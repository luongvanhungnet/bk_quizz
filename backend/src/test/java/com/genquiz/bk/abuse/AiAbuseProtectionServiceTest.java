package com.genquiz.bk.abuse;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.genquiz.bk.common.error.ApiException;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.dao.DataAccessResourceFailureException;
import tools.jackson.databind.ObjectMapper;

class AiAbuseProtectionServiceTest {
    private final UUID userId = UUID.randomUUID();
    private final AbuseRequestIdentityService identities = mock(AbuseRequestIdentityService.class);
    private final AccountReputationService reputation = mock(AccountReputationService.class);
    private final AtomicAbuseStore store = mock(AtomicAbuseStore.class);
    private final AiCostEstimator costs = mock(AiCostEstimator.class);
    private final ChallengeVerifier challenge = mock(ChallengeVerifier.class);
    private AiAbuseProtectionService service;

    @BeforeEach
    void setUp() {
        when(identities.current()).thenReturn(new AbuseRequestIdentity("ip", "device", null));
        when(reputation.assess(userId)).thenReturn(new RiskAssessment(50, 0.1,
                ServiceLevel.NORMAL, List.of()));
        when(costs.estimate(anyString(), anyInt())).thenReturn(new BigDecimal("0.02"));
        service = new AiAbuseProtectionService(AntiAbuseTestProperties.enabled(), identities,
                reputation, store, costs, challenge, new ObjectMapper(),
                Clock.fixed(Instant.parse("2026-09-04T00:00:00Z"), ZoneOffset.UTC));
    }

    @Test
    void allowsRequestOnlyAfterAtomicMultiDimensionalCheck() {
        when(store.admit(any(), anyString(), any(), anyString(), any(), any(), any(), any()))
                .thenReturn(AiAdmissionDecision.ALLOWED);
        AiAdmissionContext result = service.admitDirect(userId, "quiz_generation", "gemini", 10);
        assertThat(result.concurrencyReserved()).isTrue();
        assertThat(result.ipHash()).isEqualTo("ip");
        verify(store).admit(any(), anyString(), any(), anyString(), any(), any(), any(), any());
    }

    @ParameterizedTest
    @EnumSource(value = AiAdmissionDecision.class, names = {
            "USER_RATE_LIMIT", "IP_RATE_LIMIT", "DEVICE_RATE_LIMIT",
            "DAILY_QUOTA", "COST_BUDGET", "USER_CONCURRENCY",
            "IP_CONCURRENCY", "DEVICE_CONCURRENCY"})
    void rejectsEveryLimitDimension(AiAdmissionDecision decision) {
        when(store.admit(any(), anyString(), any(), anyString(), any(), any(), any(), any())).thenReturn(decision);
        assertThatThrownBy(() -> service.admitDirect(userId, "quiz_generation", "gemini", 10))
                .isInstanceOf(ApiException.class)
                .extracting(value -> ((ApiException) value).status().value())
                .isEqualTo(429);
    }

    @Test
    void blockedAccountCannotUseExpensiveAi() {
        when(reputation.assess(userId)).thenReturn(new RiskAssessment(0, 1,
                ServiceLevel.BLOCKED, List.of()));
        assertThatThrownBy(() -> service.admitDirect(userId, "quiz_generation", "gemini", 1))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> assertThat(exception.code()).isEqualTo("RISK_RESTRICTED"));
    }

    @Test
    void redisFailureFailsClosedForExpensiveAi() {
        when(store.admit(any(), anyString(), any(), anyString(), any(), any(), any(), any()))
                .thenThrow(new DataAccessResourceFailureException("offline"));
        assertThatThrownBy(() -> service.admitDirect(userId, "quiz_generation", "gemini", 1))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> assertThat(exception.code()).isEqualTo("ABUSE_PROTECTION_UNAVAILABLE"));
    }

    @Test
    void directConcurrencyCanAlwaysBeReleasedAfterDownstreamException() {
        when(store.admit(any(), anyString(), any(), anyString(), any(), any(), any(), any()))
                .thenReturn(AiAdmissionDecision.ALLOWED);
        AiAdmissionContext admission = service.admitDirect(userId, "attempt_ai_chat", "tutor", 1);
        try {
            throw new IllegalStateException("downstream failed");
        } catch (IllegalStateException ignored) {
            service.releaseDirect(userId, admission);
        }
        verify(store).release(userId, admission.leaseId(), "ip", "device");
    }
}
