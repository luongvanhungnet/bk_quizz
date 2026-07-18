package com.genquiz.bk.community;

import com.genquiz.bk.attempt.Attempt;
import com.genquiz.bk.attempt.AttemptStatus;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.quiz.Quiz;
import com.genquiz.bk.quiz.QuizRepository;
import com.genquiz.bk.topic.TopicRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CommunityServiceTest {
    @Mock BookmarkRepository bookmarks;
    @Mock RatingRepository ratings;
    @Mock QuizStatisticsRepository statistics;
    @Mock CommunityAttemptRepository attempts;
    @Mock QuizRepository quizzes;
    @Mock TopicRepository topics;
    @Mock Quiz quiz;

    @Test
    void ratingRequiresSubmittedAttemptOwnedBySameUserAndQuiz() {
        UUID userId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        UUID attemptId = UUID.randomUUID();
        when(quizzes.findByIdAndDeletedAtIsNull(quizId)).thenReturn(Optional.of(quiz));
        when(attempts.findByIdAndUserIdAndQuizIdAndStatus(attemptId, userId, quizId,
                AttemptStatus.SUBMITTED)).thenReturn(Optional.empty());

        ApiException error = assertThrows(ApiException.class, () -> service().rate(userId, quizId,
                new CommunityDtos.RatingRequest(attemptId, 5, "Tốt")));

        assertEquals("SUBMITTED_ATTEMPT_REQUIRED", error.code());
        verify(ratings, never()).save(any());
    }

    @Test
    void successfulRatingRefreshesAggregateStatistics() {
        UUID userId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        UUID attemptId = UUID.randomUUID();
        Attempt submitted = org.mockito.Mockito.mock(Attempt.class);
        when(quizzes.findByIdAndDeletedAtIsNull(quizId)).thenReturn(Optional.of(quiz));
        when(attempts.findByIdAndUserIdAndQuizIdAndStatus(attemptId, userId, quizId,
                AttemptStatus.SUBMITTED)).thenReturn(Optional.of(submitted));
        when(ratings.findByUserIdAndQuizIdAndDeletedAtIsNull(userId, quizId)).thenReturn(Optional.empty());
        when(ratings.save(any())).thenAnswer(invocation -> invocation.getArgument(0));
        when(attempts.countDistinctLearners(quizId)).thenReturn(3L);
        when(attempts.countByQuizIdAndStatus(quizId, AttemptStatus.SUBMITTED)).thenReturn(5L);
        when(ratings.countByQuizIdAndDeletedAtIsNull(quizId)).thenReturn(2L);
        when(ratings.sumActiveRatings(quizId)).thenReturn(9L);
        when(statistics.findById(quizId)).thenReturn(Optional.empty());
        when(statistics.save(any())).thenAnswer(invocation -> invocation.getArgument(0));

        CommunityDtos.RatingResponse response = service().rate(userId, quizId,
                new CommunityDtos.RatingRequest(attemptId, 5, "Tốt"));

        assertEquals(5, response.rating());
        verify(statistics).save(any(QuizStatistics.class));
    }

    private CommunityService service() {
        return new CommunityService(bookmarks, ratings, statistics, attempts, quizzes, topics);
    }
}
