package com.genquiz.bk.explore;

import com.genquiz.bk.quiz.Difficulty;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class ExploreDtos {
    private ExploreDtos() {}
    public record QuizSummary(UUID id, String title, Difficulty difficulty, int durationMinutes,
                              long questionCount, Instant publishedAt) {}
    public record TopicSummary(UUID id, String title, String description, UUID ownerId, String ownerUsername,
                               long quizCount, long learnerCount, long bookmarkCount, Instant publishedAt) {}
    public record TopicDetail(TopicSummary topic, List<QuizSummary> quizzes) {}
    public record SavedTopic(TopicSummary topic, Instant savedAt) {}
}
