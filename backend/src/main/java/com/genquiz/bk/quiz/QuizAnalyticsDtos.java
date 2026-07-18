package com.genquiz.bk.quiz;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public final class QuizAnalyticsDtos {
    private QuizAnalyticsDtos() {}

    public record Summary(
            long participantCount,
            long attemptCount,
            long completedCount,
            BigDecimal averagePercentage,
            BigDecimal highestPercentage,
            BigDecimal lowestPercentage,
            long averageDurationSeconds) {}

    public record Participant(
            UUID attemptId,
            UUID userId,
            String username,
            int attemptNumber,
            BigDecimal score,
            BigDecimal maxScore,
            BigDecimal percentage,
            long durationSeconds,
            Instant submittedAt) {}

    public record Question(
            UUID questionId,
            String prompt,
            long answerCount,
            long correctCount,
            BigDecimal correctRate) {}
}
