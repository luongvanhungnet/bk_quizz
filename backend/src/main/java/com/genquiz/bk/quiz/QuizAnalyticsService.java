package com.genquiz.bk.quiz;

import com.genquiz.bk.attempt.Attempt;
import com.genquiz.bk.attempt.AttemptRepository;
import com.genquiz.bk.attempt.AttemptStatus;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class QuizAnalyticsService {
    private final QuizRepository quizzes;
    private final AttemptRepository attempts;
    private final UserRepository users;

    public QuizAnalyticsService(QuizRepository quizzes, AttemptRepository attempts, UserRepository users) {
        this.quizzes = quizzes;
        this.attempts = attempts;
        this.users = users;
    }

    @Transactional(readOnly = true)
    public QuizAnalyticsDtos.Summary summary(UUID actorId, UUID quizId) {
        requireOwnerOrAdmin(actorId, quizId);
        List<Attempt> rows = attempts.findByQuizIdAndStatus(quizId, AttemptStatus.SUBMITTED);
        long participants = rows.stream().map(Attempt::getUserId).distinct().count();
        BigDecimal average = percentage(rows, Average.AVERAGE);
        BigDecimal high = percentage(rows, Average.MAX);
        BigDecimal low = percentage(rows, Average.MIN);
        long seconds = rows.isEmpty() ? 0 : Math.round(rows.stream()
                .mapToLong(this::durationSeconds).average().orElse(0));
        return new QuizAnalyticsDtos.Summary(participants, rows.size(), rows.size(), average, high, low, seconds);
    }

    @Transactional(readOnly = true)
    public Page<QuizAnalyticsDtos.Participant> participants(UUID actorId, UUID quizId, int page, int limit) {
        requireOwnerOrAdmin(actorId, quizId);
        Page<Attempt> result = attempts.findByQuizIdAndStatusOrderBySubmittedAtDesc(
                quizId, AttemptStatus.SUBMITTED, PageRequest.of(page - 1, limit));
        Map<UUID, User> people = users.findAllById(result.getContent().stream().map(Attempt::getUserId).toList())
                .stream().collect(Collectors.toMap(User::getId, Function.identity()));
        return result.map(row -> new QuizAnalyticsDtos.Participant(
                row.getId(), row.getUserId(), people.containsKey(row.getUserId())
                        ? people.get(row.getUserId()).getUsername() : "Người dùng đã xóa",
                row.getAttemptNumber(), row.getScore(), row.getMaxScore(), row.getPercentage(),
                durationSeconds(row), row.getSubmittedAt()));
    }

    @Transactional(readOnly = true)
    public List<QuizAnalyticsDtos.Question> questions(UUID actorId, UUID quizId) {
        requireOwnerOrAdmin(actorId, quizId);
        return attempts.questionAccuracy(quizId).stream().map(row -> {
            BigDecimal rate = row.getAnswerCount() == 0 ? BigDecimal.ZERO.setScale(2)
                    : BigDecimal.valueOf(row.getCorrectCount() * 100L)
                            .divide(BigDecimal.valueOf(row.getAnswerCount()), 2, RoundingMode.HALF_UP);
            return new QuizAnalyticsDtos.Question(row.getQuestionId(), row.getPrompt(), row.getAnswerCount(),
                    row.getCorrectCount(), rate);
        }).toList();
    }

    private void requireOwnerOrAdmin(UUID actorId, UUID quizId) {
        Quiz quiz = quizzes.findById(quizId).filter(q -> q.getDeletedAt() == null).orElseThrow(() ->
                new ApiException(HttpStatus.NOT_FOUND, "QUIZ_NOT_FOUND", "Không tìm thấy quiz."));
        User actor = users.findById(actorId).orElseThrow(() ->
                new ApiException(HttpStatus.UNAUTHORIZED, "USER_NOT_FOUND", "Không tìm thấy tài khoản."));
        if (!quiz.isOwnedBy(actorId) && actor.getRole() != Role.ADMIN) {
            throw new ApiException(HttpStatus.FORBIDDEN, "QUIZ_ANALYTICS_FORBIDDEN", "Bạn không có quyền xem thống kê quiz này.");
        }
    }

    private long durationSeconds(Attempt row) {
        return row.getSubmittedAt() == null ? 0
                : Math.max(0, Duration.between(row.getStartedAt(), row.getSubmittedAt()).toSeconds());
    }

    private BigDecimal percentage(List<Attempt> rows, Average operation) {
        List<BigDecimal> values = rows.stream().map(Attempt::getPercentage).filter(java.util.Objects::nonNull).toList();
        if (values.isEmpty()) return BigDecimal.ZERO.setScale(2);
        return switch (operation) {
            case MAX -> values.stream().max(BigDecimal::compareTo).orElseThrow();
            case MIN -> values.stream().min(BigDecimal::compareTo).orElseThrow();
            case AVERAGE -> values.stream().reduce(BigDecimal.ZERO, BigDecimal::add)
                    .divide(BigDecimal.valueOf(values.size()), 2, RoundingMode.HALF_UP);
        };
    }

    private enum Average { AVERAGE, MAX, MIN }
}
