package com.genquiz.bk.abuse;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "bkquiz.anti-abuse")
public record AntiAbuseProperties(
        boolean enabled,
        @NotBlank String ipHashSecret,
        @NotNull Duration rateWindow,
        @Min(1) int userRateLimit,
        @Min(1) int ipRateLimit,
        @Min(1) int deviceRateLimit,
        @NotNull Duration concurrencyTtl,
        @NotNull Duration costKeyTtl,
        @Valid Pricing pricing,
        @Valid Levels levels,
        @Valid Risk risk,
        @Valid Turnstile turnstile
) {
    public record Pricing(
            @DecimalMin("0") BigDecimal defaultInputPerMillion,
            @DecimalMin("0") BigDecimal defaultOutputPerMillion,
            @Min(1) int estimatedInputTokensPerQuestion,
            @Min(1) int estimatedOutputTokensPerQuestion
    ) {}

    public record LevelPolicy(
            @Min(0) int dailyQuota,
            @DecimalMin("0") BigDecimal dailyCostBudget,
            @Min(0) int concurrency,
            boolean challengeRequired
    ) {}

    public record Levels(LevelPolicy trusted, LevelPolicy normal, LevelPolicy caution,
                         LevelPolicy restricted, LevelPolicy blocked) {
        public LevelPolicy forLevel(ServiceLevel level) {
            return switch (level) {
                case TRUSTED -> trusted;
                case NORMAL -> normal;
                case CAUTION -> caution;
                case RESTRICTED -> restricted;
                case BLOCKED -> blocked;
            };
        }
    }

    public record Risk(
            @Min(0) int verifiedEmailTrust,
            @Min(0) int normalActivityTrust,
            @Min(0) int successfulSessionTrust,
            @DecimalMin("0") BigDecimal accountAgeTrustPerDay,
            @Min(0) int accountAgeTrustCap,
            @Min(0) int trustedMinScore,
            @Min(1) int trustedMinLegitimateActivities,
            @DecimalMin("0") BigDecimal cautionRiskScore,
            @DecimalMin("0") BigDecimal restrictedRiskScore,
            @DecimalMin("0") BigDecimal blockedRiskScore
    ) {}

    public record Turnstile(boolean enabled, String secretKey, @NotBlank String verifyUrl) {}
}
