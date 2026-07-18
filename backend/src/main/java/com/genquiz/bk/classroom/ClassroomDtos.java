package com.genquiz.bk.classroom;

import com.genquiz.bk.attempt.AnswerReleasePolicy;
import com.genquiz.bk.attempt.Attempt;
import com.genquiz.bk.attempt.AttemptStatus;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public final class ClassroomDtos {
    private ClassroomDtos() {}

    public record SaveRequest(
            @NotBlank @Size(max = 200) String name,
            @Size(max = 5000) String description
    ) {}

    public record JoinRequest(
            @NotBlank(message = "Mã lớp không được để trống.")
            @Pattern(regexp = "[A-Za-z0-9]{6,12}",
                    message = "Mã lớp phải gồm 6–12 chữ cái hoặc chữ số.")
            String joinCode
    ) {}

    public record JoinSettingsRequest(boolean enabled) {}
    public record JoinPreview(UUID classroomId, String name, String ownerUsername, long memberCount, boolean joinEnabled) {}

    public record AddMemberRequest(
            @NotNull UUID userId,
            @NotNull ClassroomMemberRole role
    ) {}

    public record ClassroomResponse(
            UUID id,
            UUID ownerId,
            String name,
            String description,
            String joinCode,
            boolean joinEnabled,
            ClassroomStatus status,
            Instant archivedAt,
            Instant createdAt,
            Instant updatedAt,
            long version
    ) {
        public static ClassroomResponse from(Classroom classroom) {
            return new ClassroomResponse(classroom.getId(), classroom.getOwnerId(), classroom.getName(),
                    classroom.getDescription(), classroom.getJoinCode(), classroom.isJoinEnabled(), classroom.getStatus(),
                    classroom.getArchivedAt(), classroom.getCreatedAt(), classroom.getUpdatedAt(), classroom.getVersion());
        }
    }

    public record MemberResponse(
            UUID id,
            UUID userId,
            String username,
            ClassroomMemberRole role,
            ClassroomMemberStatus status,
            Instant joinedAt
    ) {}

    public record AssignmentRequest(
            @NotNull UUID quizId,
            @NotBlank @Size(max = 200) String title,
            @Size(max = 10000) String instructions,
            Instant opensAt,
            Instant dueAt,
            @Min(1) @Max(1440) int durationMinutes,
            @Min(1) @Max(100) int maxAttempts,
            @NotNull AnswerReleasePolicy answerReleasePolicy,
            Boolean showScore, Boolean allowReview, Boolean shuffleQuestions,
            Boolean shuffleOptions, Boolean showLeaderboard
    ) {}

    public record AssignmentUpdateRequest(
            @NotBlank @Size(max = 200) String title,
            @Size(max = 10000) String instructions,
            Instant opensAt,
            Instant dueAt,
            @Min(1) @Max(1440) int durationMinutes,
            @Min(1) @Max(100) int maxAttempts,
            @NotNull AnswerReleasePolicy answerReleasePolicy,
            Boolean showScore, Boolean allowReview, Boolean shuffleQuestions,
            Boolean shuffleOptions, Boolean showLeaderboard
    ) {}

    public record AssignmentResponse(
            UUID id,
            UUID classroomId,
            UUID quizId,
            UUID createdBy,
            String title,
            String instructions,
            AssignmentStatus status,
            Instant opensAt,
            Instant dueAt,
            int durationMinutes,
            int maxAttempts,
            AnswerReleasePolicy answerReleasePolicy,
            AssignmentShareKind shareKind, boolean showScore, boolean allowReview,
            boolean shuffleQuestions, boolean shuffleOptions, boolean showLeaderboard,
            Instant publishedAt,
            Instant closedAt,
            Instant createdAt,
            Instant updatedAt,
            long version
    ) {
        public static AssignmentResponse from(Assignment assignment) {
            return new AssignmentResponse(assignment.getId(), assignment.getClassroomId(), assignment.getQuizId(),
                    assignment.getCreatedBy(), assignment.getTitle(), assignment.getInstructions(), assignment.getStatus(),
                    assignment.getOpensAt(), assignment.getDueAt(), assignment.getDurationMinutes(),
                    assignment.getMaxAttempts(), assignment.getAnswerReleasePolicy(), assignment.getShareKind(),
                    assignment.isShowScore(), assignment.isAllowReview(), assignment.isShuffleQuestions(),
                    assignment.isShuffleOptions(), assignment.isShowLeaderboard(), assignment.getPublishedAt(),
                    assignment.getClosedAt(), assignment.getCreatedAt(), assignment.getUpdatedAt(), assignment.getVersion());
        }
    }

    public record SubmissionResponse(
            UUID attemptId,
            UUID userId,
            String username,
            AttemptStatus status,
            int attemptNumber,
            BigDecimal score,
            BigDecimal maxScore,
            BigDecimal percentage,
            boolean timedOut,
            Instant startedAt,
            Instant submittedAt
    ) {
        public static SubmissionResponse from(Attempt attempt, String username) {
            return new SubmissionResponse(attempt.getId(), attempt.getUserId(), username, attempt.getStatus(),
                    attempt.getAttemptNumber(), attempt.getScore(), attempt.getMaxScore(), attempt.getPercentage(),
                    attempt.isTimedOut(), attempt.getStartedAt(), attempt.getSubmittedAt());
        }
    }
}
