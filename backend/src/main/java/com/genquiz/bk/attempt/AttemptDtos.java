package com.genquiz.bk.attempt;

import com.genquiz.bk.quiz.QuestionType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class AttemptDtos {
    private AttemptDtos() {}

    public record StartRequest(UUID assignmentId) {}

    public record Option(UUID id, String text, int position) {}

    /** Safe while taking: contains neither correctness nor explanations. */
    public record Question(
            UUID snapshotId,
            QuestionType type,
            String prompt,
            BigDecimal points,
            int position,
            List<Option> options) {}

    public record SavedAnswer(UUID snapshotId, List<UUID> selectedOptionIds, String textAnswer, long version) {}

    public record AttemptResponse(
            UUID id,
            UUID quizId,
            UUID assignmentId,
            AttemptStatus status,
            Instant startedAt,
            Instant expiresAt,
            Instant submittedAt,
            long version,
            List<Question> questions,
            List<SavedAnswer> answers) {}

    public record AnswerInput(
            @NotNull UUID snapshotId,
            @Size(max = 4) List<UUID> selectedOptionIds,
            @Size(max = 5000) String textAnswer) {}

    public record AutosaveRequest(long attemptVersion, @NotNull List<@Valid AnswerInput> answers) {}

    public record QuestionResult(
            UUID snapshotId,
            Boolean correct,
            BigDecimal awardedPoints,
            BigDecimal maxPoints,
            List<UUID> correctOptionIds,
            List<String> acceptedAnswers,
            String explanation) {}

    public record ResultResponse(
            UUID attemptId,
            UUID quizId,
            AttemptStatus status,
            BigDecimal score,
            BigDecimal maxScore,
            BigDecimal percentage,
            boolean timedOut,
            boolean answersReleased,
            Instant submittedAt,
            List<QuestionResult> questions) {}

    public record HistoryItem(
            UUID id, UUID quizId, UUID assignmentId, AttemptStatus status, BigDecimal score,
            BigDecimal maxScore, BigDecimal percentage, Instant startedAt, Instant submittedAt) {
        public static HistoryItem from(Attempt attempt) {
            return new HistoryItem(attempt.getId(), attempt.getQuizId(), attempt.getAssignmentId(),
                    attempt.getStatus(), attempt.getScore(), attempt.getMaxScore(), attempt.getPercentage(),
                    attempt.getStartedAt(), attempt.getSubmittedAt());
        }
    }
}
