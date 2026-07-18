package com.genquiz.bk.user;

import com.genquiz.bk.attempt.AttemptRepository;
import com.genquiz.bk.attempt.AttemptStatus;
import com.genquiz.bk.quiz.QuizRepository;
import com.genquiz.bk.topic.TopicRepository;
import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DashboardService {
    private final TopicRepository topics;
    private final QuizRepository quizzes;
    private final AttemptRepository attempts;
    public DashboardService(TopicRepository topics, QuizRepository quizzes, AttemptRepository attempts) {
        this.topics = topics; this.quizzes = quizzes; this.attempts = attempts;
    }
    @Transactional(readOnly = true)
    public DashboardDtos.Response get(UUID userId) {
        var stats = new DashboardDtos.Stats(topics.countByOwnerIdAndDeletedAtIsNull(userId),
                quizzes.countByOwnerIdAndDeletedAtIsNull(userId),
                attempts.countByUserIdAndStatus(userId, AttemptStatus.SUBMITTED),
                valueOrZero(attempts.averagePercentage(userId)));
        var recentTopics = topics.findTop5ByOwnerIdAndDeletedAtIsNullOrderByUpdatedAtDesc(userId).stream()
                .map(t -> new DashboardDtos.RecentTopic(t.getId(), t.getTitle(), t.getDescription(),
                        t.getVisibility(), t.getStatus(), t.getUpdatedAt())).toList();
        var activities = attempts.findDashboardActivities(userId, PageRequest.of(0, 10)).stream()
                .map(a -> new DashboardDtos.Activity(a.attemptId(), a.quizId(), a.quizTitle(),
                        a.status(), a.percentage(), a.occurredAt()))
                .toList();
        return new DashboardDtos.Response(stats, recentTopics, activities);
    }
    private static BigDecimal valueOrZero(BigDecimal value) { return value == null ? BigDecimal.ZERO : value; }
}
