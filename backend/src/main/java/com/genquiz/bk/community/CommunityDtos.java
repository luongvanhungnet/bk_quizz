package com.genquiz.bk.community;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public final class CommunityDtos {
    private CommunityDtos() {}

    public record BookmarkResponse(UUID quizId, Instant createdAt) {
        public static BookmarkResponse from(Bookmark bookmark) {
            return new BookmarkResponse(bookmark.getQuizId(), bookmark.getCreatedAt());
        }
    }

    public record RatingRequest(
            @NotNull UUID attemptId,
            @Min(1) @Max(5) int rating,
            @Size(max = 5000) String review
    ) {}

    public record RatingResponse(
            UUID id,
            UUID quizId,
            UUID userId,
            UUID attemptId,
            int rating,
            String review,
            Instant createdAt,
            Instant updatedAt,
            long version
    ) {
        public static RatingResponse from(Rating rating) {
            return new RatingResponse(rating.getId(), rating.getQuizId(), rating.getUserId(), rating.getAttemptId(),
                    rating.getRating(), rating.getReview(), rating.getCreatedAt(), rating.getUpdatedAt(),
                    rating.getVersion());
        }
    }

    public record StatisticsResponse(
            UUID quizId,
            long learnerCount,
            long attemptCount,
            long ratingCount,
            BigDecimal averageRating,
            Instant updatedAt
    ) {
        public static StatisticsResponse from(QuizStatistics statistics) {
            BigDecimal average = statistics.getRatingCount() == 0 ? null
                    : BigDecimal.valueOf(statistics.getRatingSum())
                    .divide(BigDecimal.valueOf(statistics.getRatingCount()), 2, java.math.RoundingMode.HALF_UP);
            return new StatisticsResponse(statistics.getQuizId(), statistics.getLearnerCount(),
                    statistics.getAttemptCount(), statistics.getRatingCount(), average, statistics.getUpdatedAt());
        }
    }
}
