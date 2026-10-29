package com.genquiz.bk.analytics;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class AdminAnalyticsDtos {
    private AdminAnalyticsDtos() {}

    public record Point(LocalDate date, long value) {}
    public record MoneyPoint(LocalDate date, BigDecimal value) {}
    public record Availability(boolean available, String reason) {}
    public record Overview(long dau, long wau, long mau, long newUsers, long activatedUsers,
                           long quizGenerations, long quizzesCompleted, long aiGenerations,
                           BigDecimal aiCost, BigDecimal aiCostPerActiveUser,
                           BigDecimal aiCostPerQuiz, double quotaExhaustionRate,
                           long blockedAiRequests, long highRiskUsers,
                           List<Point> activeUsersSeries, List<Point> registrationsSeries,
                           Availability subscriptionConversion) {}
    public record RetentionPoint(LocalDate cohortDate, long cohortSize, long retainedUsers,
                                 int day, double rate) {}
    public record UserAnalytics(List<Point> registrations, List<Point> activations,
                                List<RetentionPoint> d1, List<RetentionPoint> d7,
                                List<RetentionPoint> d30) {}
    public record AiModelUsage(String provider, String model, long requests, long successes,
                               long failures, long inputTokens, long outputTokens,
                               BigDecimal estimatedCost, BigDecimal actualCost) {}
    public record CostUser(UUID userId, String username, String email, long requests,
                           BigDecimal cost) {}
    public record AiAnalytics(List<MoneyPoint> dailyCost, List<Point> dailyRequests,
                              List<AiModelUsage> byModel, List<CostUser> highestCostUsers,
                              BigDecimal totalCost, double failureRate,
                              double quotaRejectionRate, double topOnePercentCostShare) {}
    public record SecurityMetric(String eventType, long count, BigDecimal preventedCost) {}
    public record Distribution(String value, long count) {}
    public record SecurityAnalytics(long blockedRequests, long rateLimitViolations,
                                    long failedLogins, long suspiciousRegistrations,
                                    long restrictedAccounts, long blockedAccounts,
                                    long highRiskUsers, BigDecimal preventedAiCost,
                                    List<SecurityMetric> events,
                                    List<Distribution> serviceLevels,
                                    List<Distribution> riskBands) {}
    public record ProductActivity(long id, String eventType, java.time.Instant occurredAt,
                                  Map<String, Object> properties) {}
}
