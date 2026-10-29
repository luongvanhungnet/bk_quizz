package com.genquiz.bk.analytics;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix="bkquiz.analytics", name="aggregation-enabled", havingValue="true", matchIfMissing=true)
public class AnalyticsAggregationScheduler {
    private final AnalyticsAggregationService service;
    public AnalyticsAggregationScheduler(AnalyticsAggregationService service) { this.service=service; }

    @Scheduled(fixedDelayString="${bkquiz.analytics.aggregation-delay:5m}")
    public void aggregate() { service.recomputeRecent(); }
}
