package com.genquiz.bk.community;

import com.genquiz.bk.attempt.AttemptStatus;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.quiz.Quiz;
import com.genquiz.bk.quiz.QuizRepository;
import com.genquiz.bk.quiz.QuizStatus;
import com.genquiz.bk.topic.Topic;
import com.genquiz.bk.topic.TopicRepository;
import com.genquiz.bk.topic.Visibility;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Service
public class CommunityService {
    private final BookmarkRepository bookmarks;
    private final RatingRepository ratings;
    private final QuizStatisticsRepository statistics;
    private final CommunityAttemptRepository attempts;
    private final QuizRepository quizzes;
    private final TopicRepository topics;

    public CommunityService(BookmarkRepository bookmarks, RatingRepository ratings,
                            QuizStatisticsRepository statistics, CommunityAttemptRepository attempts,
                            QuizRepository quizzes, TopicRepository topics) {
        this.bookmarks = bookmarks;
        this.ratings = ratings;
        this.statistics = statistics;
        this.attempts = attempts;
        this.quizzes = quizzes;
        this.topics = topics;
    }

    @Transactional
    public CommunityDtos.BookmarkResponse bookmark(UUID userId, UUID quizId) {
        Quiz quiz = requireQuiz(quizId);
        requireVisibleTo(quiz, userId);
        Bookmark bookmark = bookmarks.findByUserIdAndQuizId(userId, quizId)
                .orElseGet(() -> bookmarks.save(new Bookmark(userId, quizId, Instant.now())));
        return CommunityDtos.BookmarkResponse.from(bookmark);
    }

    @Transactional
    public void unbookmark(UUID userId, UUID quizId) {
        bookmarks.deleteByUserIdAndQuizId(userId, quizId);
    }

    @Transactional(readOnly = true)
    public Page<CommunityDtos.BookmarkResponse> bookmarks(UUID userId, int page, int limit) {
        return bookmarks.findByUserIdOrderByCreatedAtDesc(userId, PageRequest.of(page - 1, limit))
                .map(CommunityDtos.BookmarkResponse::from);
    }

    @Transactional
    public CommunityDtos.RatingResponse rate(UUID userId, UUID quizId, CommunityDtos.RatingRequest request) {
        requireQuiz(quizId);
        attempts.findByIdAndUserIdAndQuizIdAndStatus(request.attemptId(), userId, quizId, AttemptStatus.SUBMITTED)
                .orElseThrow(() -> new ApiException(HttpStatus.FORBIDDEN, "SUBMITTED_ATTEMPT_REQUIRED",
                        "Bạn cần hoàn thành bài kiểm tra trước khi đánh giá."));
        Instant now = Instant.now();
        Rating rating = ratings.findByUserIdAndQuizIdAndDeletedAtIsNull(userId, quizId)
                .map(existing -> {
                    existing.update(request.attemptId(), request.rating(), request.review(), now);
                    return existing;
                })
                .orElseGet(() -> new Rating(userId, quizId, request.attemptId(), request.rating(),
                        request.review(), now));
        ratings.save(rating);
        ratings.flush();
        refreshStatistics(quizId, now);
        return CommunityDtos.RatingResponse.from(rating);
    }

    @Transactional
    public void deleteRating(UUID userId, UUID quizId) {
        Rating rating = ratings.findByUserIdAndQuizIdAndDeletedAtIsNull(userId, quizId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "RATING_NOT_FOUND",
                        "Không tìm thấy đánh giá."));
        Instant now = Instant.now();
        rating.softDelete(now);
        ratings.flush();
        refreshStatistics(quizId, now);
    }

    @Transactional(readOnly = true)
    public Page<CommunityDtos.RatingResponse> ratings(UUID userId, UUID quizId, int page, int limit) {
        Quiz quiz = requireQuiz(quizId);
        requireVisibleTo(quiz, userId);
        return ratings.findByQuizIdAndDeletedAtIsNullOrderByCreatedAtDesc(quizId, PageRequest.of(page - 1, limit))
                .map(CommunityDtos.RatingResponse::from);
    }

    @Transactional
    public CommunityDtos.StatisticsResponse statistics(UUID userId, UUID quizId) {
        Quiz quiz = requireQuiz(quizId);
        requireVisibleTo(quiz, userId);
        return CommunityDtos.StatisticsResponse.from(refreshStatistics(quizId, Instant.now()));
    }

    private QuizStatistics refreshStatistics(UUID quizId, Instant now) {
        long learnerCount = attempts.countDistinctLearners(quizId);
        long attemptCount = attempts.countByQuizIdAndStatus(quizId, AttemptStatus.SUBMITTED);
        long ratingCount = ratings.countByQuizIdAndDeletedAtIsNull(quizId);
        Long sum = ratings.sumActiveRatings(quizId);
        QuizStatistics current = statistics.findById(quizId).orElseGet(() -> new QuizStatistics(quizId));
        current.refresh(learnerCount, attemptCount, ratingCount, sum == null ? 0 : sum, now);
        return statistics.save(current);
    }

    private Quiz requireQuiz(UUID quizId) {
        return quizzes.findByIdAndDeletedAtIsNull(quizId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "QUIZ_NOT_FOUND",
                        "Không tìm thấy bài kiểm tra."));
    }

    private void requireVisibleTo(Quiz quiz, UUID userId) {
        if (quiz.isOwnedBy(userId)) return;
        if (quiz.getStatus() == QuizStatus.PUBLISHED && quiz.getVisibility() == Visibility.PUBLIC) {
            Topic topic = topics.findByIdAndDeletedAtIsNull(quiz.getTopicId()).orElse(null);
            if (topic != null && topic.isPubliclyVisible()) return;
        }
        if (attempts.existsByQuizIdAndUserIdAndStatus(quiz.getId(), userId, AttemptStatus.SUBMITTED)) return;
        throw new ApiException(HttpStatus.FORBIDDEN, "QUIZ_ACCESS_DENIED",
                "Bạn không có quyền truy cập hoạt động cộng đồng của bài kiểm tra này.");
    }
}
