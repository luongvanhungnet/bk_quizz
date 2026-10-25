package com.genquiz.bk.analytics;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class AdminAnalyticsServiceTest {
    @Test
    void topOnePercentUsesCeilingAndHighestCostUsers() {
        List<BigDecimal> costs=new ArrayList<>();
        costs.add(new BigDecimal("100"));
        for(int i=0;i<199;i++) costs.add(BigDecimal.ONE);

        assertThat(AdminAnalyticsService.topOnePercentCostShare(costs))
                .isCloseTo(101d/299d,org.assertj.core.data.Offset.offset(0.000001));
    }

    @Test
    void topOnePercentIsZeroForEmptyOrZeroCostData() {
        assertThat(AdminAnalyticsService.topOnePercentCostShare(List.of())).isZero();
        assertThat(AdminAnalyticsService.topOnePercentCostShare(List.of(BigDecimal.ZERO))).isZero();
    }
}
