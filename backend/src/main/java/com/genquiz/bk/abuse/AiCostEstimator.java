package com.genquiz.bk.abuse;

import java.math.BigDecimal;
import java.util.Map;

public interface AiCostEstimator {
    BigDecimal estimate(String model, int questionCount);
    BigDecimal actual(String model, Map<String, Integer> usage);
}
