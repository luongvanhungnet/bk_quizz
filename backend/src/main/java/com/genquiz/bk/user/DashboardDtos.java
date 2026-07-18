package com.genquiz.bk.user;

import com.genquiz.bk.attempt.AttemptStatus;
import com.genquiz.bk.topic.TopicStatus;
import com.genquiz.bk.topic.Visibility;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class DashboardDtos {
    private DashboardDtos() {}
    public record Stats(long topicCount, long quizCount, long submittedAttemptCount, BigDecimal averagePercentage) {}
    public record RecentTopic(UUID id, String title, String description, Visibility visibility, TopicStatus status,
                              Instant updatedAt) {}
    public record Activity(UUID attemptId, UUID quizId, String quizTitle, AttemptStatus status,
                           BigDecimal percentage, Instant occurredAt) {}
    public record Response(Stats stats, List<RecentTopic> recentTopics, List<Activity> recentActivities) {}
}
