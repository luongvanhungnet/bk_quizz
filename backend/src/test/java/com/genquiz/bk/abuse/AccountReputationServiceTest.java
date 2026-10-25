package com.genquiz.bk.abuse;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.sql.Timestamp;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.ObjectMapper;

class AccountReputationServiceTest {
    private final UUID userId = UUID.randomUUID();
    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final UserRepository users = mock(UserRepository.class);

    @Test
    void newUnverifiedAccountGetsReducedCautionLevel() {
        RiskAssessment result = assess(new User("new-user", "new@example.com", "hash"), 0, 0, "0");
        assertThat(result.serviceLevel()).isEqualTo(ServiceLevel.CAUTION);
        assertThat(AntiAbuseTestProperties.enabled().levels().caution().dailyQuota())
                .isLessThan(AntiAbuseTestProperties.enabled().levels().normal().dailyQuota());
    }

    @Test
    void verifiedLegitimateActivityCanImproveTrust() {
        User user = new User("normal-user", "normal@example.com", "hash");
        user.verifyEmail();
        RiskAssessment result = assess(user, 12, 12, "0");
        assertThat(result.trustScore()).isGreaterThanOrEqualTo(75);
        assertThat(result.serviceLevel()).isEqualTo(ServiceLevel.TRUSTED);
    }

    @Test
    void accountAgeAloneCanNeverCreateTrustedStatus() {
        RiskAssessment result = assess(new User("old-user", "old@example.com", "hash"), 0, 0, "0");
        assertThat(result.serviceLevel()).isNotEqualTo(ServiceLevel.TRUSTED);
    }

    @Test
    void repeatedAbuseMovesAccountTowardRestricted() {
        User user = new User("risky-user", "risky@example.com", "hash");
        user.verifyEmail();
        RiskAssessment result = assess(user, 5, 5, "0.70");
        assertThat(result.riskScore()).isEqualTo(0.70);
        assertThat(result.serviceLevel()).isEqualTo(ServiceLevel.RESTRICTED);
        assertThat(result.trustScore()).isLessThan(50);
    }

    private RiskAssessment assess(User user, int activities, int sessions, String risk) {
        when(users.findByIdAndDeletedAtIsNull(userId)).thenReturn(Optional.of(user));
        when(jdbc.queryForMap(anyString(), eq(userId))).thenReturn(Map.of(
                "legitimate_activity_count", activities,
                "successful_session_count", sessions));
        when(jdbc.queryForObject(anyString(), eq(BigDecimal.class), eq(userId), any(Timestamp.class)))
                .thenReturn(new BigDecimal(risk));
        var service = new AccountReputationService(jdbc, users, new ObjectMapper(),
                AntiAbuseTestProperties.enabled(),
                Clock.fixed(Instant.parse("2026-09-04T00:00:00Z"), ZoneOffset.UTC));
        return service.assess(userId);
    }
}
