package com.genquiz.bk.analytics;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "bkquiz.analytics")
public record AnalyticsProperties(boolean aggregationEnabled,
                                  @NotNull Duration aggregationDelay,
                                  @Min(1) @Max(3660) int maxRangeDays) {}
