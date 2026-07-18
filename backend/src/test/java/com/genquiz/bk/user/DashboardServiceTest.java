package com.genquiz.bk.user;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import com.genquiz.bk.attempt.AttemptRepository;
import com.genquiz.bk.attempt.AttemptStatus;
import com.genquiz.bk.attempt.DashboardActivityRow;
import com.genquiz.bk.quiz.QuizRepository;
import com.genquiz.bk.topic.TopicRepository;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Pageable;

@ExtendWith(MockitoExtension.class)
class DashboardServiceTest {
    @Mock TopicRepository topics;
    @Mock QuizRepository quizzes;
    @Mock AttemptRepository attempts;

    @Test
    void returnsZeroStatsAndMapsProjectionWithoutLoadingAttemptEntities() {
        UUID userId = UUID.randomUUID();
        UUID attemptId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        Instant occurredAt = Instant.parse("2026-07-16T10:00:00Z");
        when(attempts.averagePercentage(userId)).thenReturn(null);
        when(topics.findTop5ByOwnerIdAndDeletedAtIsNullOrderByUpdatedAtDesc(userId)).thenReturn(List.of());
        when(attempts.findDashboardActivities(any(UUID.class), any(Pageable.class))).thenReturn(List.of(
                new DashboardActivityRow(attemptId, quizId, "Mạng máy tính", AttemptStatus.SUBMITTED,
                        new BigDecimal("82.50"), occurredAt)));

        DashboardDtos.Response result = new DashboardService(topics, quizzes, attempts).get(userId);

        assertThat(result.stats().averagePercentage()).isEqualByComparingTo(BigDecimal.ZERO);
        assertThat(result.recentActivities()).containsExactly(new DashboardDtos.Activity(
                attemptId, quizId, "Mạng máy tính", AttemptStatus.SUBMITTED,
                new BigDecimal("82.50"), occurredAt));
    }
}
