package com.genquiz.bk.abuse;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class ConfigurableAiCostEstimator implements AiCostEstimator {
    private static final BigDecimal MILLION = BigDecimal.valueOf(1_000_000);
    private final AntiAbuseProperties properties;

    public ConfigurableAiCostEstimator(AntiAbuseProperties properties) {
        this.properties = properties;
    }

    @Override
    public BigDecimal estimate(String model, int questionCount) {
        int count = Math.max(1, questionCount);
        return cost(
                (long) count * properties.pricing().estimatedInputTokensPerQuestion(),
                (long) count * properties.pricing().estimatedOutputTokensPerQuestion());
    }

    @Override
    public BigDecimal actual(String model, Map<String, Integer> usage) {
        if (usage == null || usage.isEmpty()) return BigDecimal.ZERO;
        long input = Math.max(0, usage.getOrDefault("inputTokens",
                usage.getOrDefault("promptTokens", 0)));
        long output = Math.max(0, usage.getOrDefault("outputTokens",
                usage.getOrDefault("completionTokens", 0)));
        return cost(input, output);
    }

    private BigDecimal cost(long inputTokens, long outputTokens) {
        return properties.pricing().defaultInputPerMillion()
                .multiply(BigDecimal.valueOf(inputTokens)).divide(MILLION, 8, RoundingMode.HALF_UP)
                .add(properties.pricing().defaultOutputPerMillion()
                        .multiply(BigDecimal.valueOf(outputTokens)).divide(MILLION, 8, RoundingMode.HALF_UP));
    }
}
