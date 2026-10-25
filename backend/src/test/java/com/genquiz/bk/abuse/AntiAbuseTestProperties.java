package com.genquiz.bk.abuse;

import java.math.BigDecimal;
import java.time.Duration;

final class AntiAbuseTestProperties {
    private AntiAbuseTestProperties() {}

    static AntiAbuseProperties enabled() {
        return new AntiAbuseProperties(true, "test-secret-at-least-thirty-two-characters", Duration.ofHours(1),
                20, 40, 30, Duration.ofMinutes(30), Duration.ofDays(3),
                new AntiAbuseProperties.Pricing(new BigDecimal("0.10"), new BigDecimal("0.40"), 900, 500),
                new AntiAbuseProperties.Levels(
                        policy(100, "2.00", 3, false), policy(40, "0.80", 2, false),
                        policy(15, "0.30", 1, false), policy(3, "0.08", 1, true),
                        policy(0, "0", 0, true)),
                new AntiAbuseProperties.Risk(15, 3, 1, new BigDecimal("0.10"), 10,
                        75, 10, new BigDecimal("0.30"), new BigDecimal("0.60"),
                        new BigDecimal("0.90")),
                new AntiAbuseProperties.Turnstile(false, "", "https://example.invalid/verify"));
    }

    private static AntiAbuseProperties.LevelPolicy policy(int quota, String budget,
                                                           int concurrency, boolean challenge) {
        return new AntiAbuseProperties.LevelPolicy(quota, new BigDecimal(budget), concurrency, challenge);
    }
}
