package com.genquiz.bk.abuse;

import static org.assertj.core.api.Assertions.assertThat;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ConfigurableAiCostEstimatorTest {
    private final ConfigurableAiCostEstimator estimator =
            new ConfigurableAiCostEstimator(AntiAbuseTestProperties.enabled());

    @Test
    void actualTokenCostIsIndependentFromRequestCountQuota() {
        assertThat(estimator.actual("gemini", Map.of("inputTokens", 1_000_000,
                "outputTokens", 1_000_000))).isEqualByComparingTo("0.50000000");
        assertThat(estimator.estimate("gemini", 20)).isPositive();
    }
}
