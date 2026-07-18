package com.genquiz.bk.attempt;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "attempts", uniqueConstraints = {
        @UniqueConstraint(name = "uk_attempt_submission_key", columnNames = {"user_id", "submission_idempotency_key"})
})
public class Attempt {
    @Id
    private UUID id;

    @Column(name = "quiz_id", nullable = false, updatable = false)
    private UUID quizId;

    @Column(name = "assignment_id", updatable = false)
    private UUID assignmentId;

    @Column(name = "user_id", nullable = false, updatable = false)
    private UUID userId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private AttemptStatus status;

    @Column(name = "attempt_number", nullable = false, updatable = false)
    private int attemptNumber;

    @Enumerated(EnumType.STRING)
    @Column(name = "answer_release_policy", nullable = false, length = 30)
    private AnswerReleasePolicy answerReleasePolicy;

    @Column(name = "assignment_due_at")
    private Instant assignmentDueAt;

    @Column(name = "started_at", nullable = false, updatable = false)
    private Instant startedAt;

    @Column(name = "deadline_at", nullable = false)
    private Instant expiresAt;

    @Column(name = "last_saved_at")
    private Instant lastSavedAt;

    @Column(name = "submitted_at")
    private Instant submittedAt;

    @Column(name = "timed_out", nullable = false)
    private boolean timedOut;
    @Column(name = "show_score", nullable = false) private boolean showScore = true;
    @Column(name = "allow_review", nullable = false) private boolean allowReview = true;

    @Column(precision = 10, scale = 2)
    private BigDecimal score;

    @Column(name = "max_score", precision = 10, scale = 2)
    private BigDecimal maxScore;

    @Column(precision = 5, scale = 2)
    private BigDecimal percentage;

    @Column(name = "correct_count")
    private Integer correctCount;

    @Column(name = "total_questions", nullable = false, updatable = false)
    private int totalQuestions;

    @Column(name = "submission_idempotency_key", length = 200)
    private String submissionKey;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected Attempt() {}

    public Attempt(UUID quizId, UUID assignmentId, UUID userId, int attemptNumber, int totalQuestions,
                   Instant startedAt, Instant expiresAt, AnswerReleasePolicy releasePolicy, Instant assignmentDueAt) {
        this(quizId, assignmentId, userId, attemptNumber, totalQuestions, startedAt, expiresAt,
                releasePolicy, assignmentDueAt, true, true);
    }

    public Attempt(UUID quizId, UUID assignmentId, UUID userId, int attemptNumber, int totalQuestions,
                   Instant startedAt, Instant expiresAt, AnswerReleasePolicy releasePolicy, Instant assignmentDueAt,
                   boolean showScore, boolean allowReview) {
        this.id = UUID.randomUUID();
        this.quizId = quizId;
        this.assignmentId = assignmentId;
        this.userId = userId;
        this.status = AttemptStatus.IN_PROGRESS;
        this.attemptNumber = attemptNumber;
        this.totalQuestions = totalQuestions;
        this.startedAt = startedAt;
        this.expiresAt = expiresAt;
        this.answerReleasePolicy = releasePolicy;
        this.assignmentDueAt = assignmentDueAt;
        this.showScore = showScore;
        this.allowReview = allowReview;
        this.createdAt = startedAt;
        this.updatedAt = startedAt;
        this.lastSavedAt = startedAt;
    }

    public void touch(Instant now) {
        if (status != AttemptStatus.IN_PROGRESS) throw new IllegalStateException("Lượt làm bài đã kết thúc");
        updatedAt = now;
        lastSavedAt = now;
    }

    public void submit(BigDecimal score, BigDecimal maxScore, int correctCount, String submissionKey, Instant now) {
        if (status != AttemptStatus.IN_PROGRESS) throw new IllegalStateException("Lượt làm bài đã kết thúc");
        this.score = score.setScale(2, RoundingMode.HALF_UP);
        this.maxScore = maxScore.setScale(2, RoundingMode.HALF_UP);
        this.percentage = maxScore.signum() == 0 ? BigDecimal.ZERO.setScale(2)
                : score.multiply(BigDecimal.valueOf(100)).divide(maxScore, 2, RoundingMode.HALF_UP);
        this.submissionKey = submissionKey;
        this.correctCount = correctCount;
        this.submittedAt = now;
        this.timedOut = now.isAfter(expiresAt);
        this.status = AttemptStatus.SUBMITTED;
        this.updatedAt = now;
    }

    public void expire(Instant now) {
        if (status == AttemptStatus.IN_PROGRESS) {
            status = AttemptStatus.EXPIRED;
            timedOut = true;
            updatedAt = now;
        }
    }

    public boolean isOwnedBy(UUID actorId) { return userId.equals(actorId); }
    public boolean answersMayBeReleased(Instant now) {
        return status == AttemptStatus.SUBMITTED && (answerReleasePolicy == AnswerReleasePolicy.IMMEDIATE
                || (answerReleasePolicy == AnswerReleasePolicy.AFTER_DUE_DATE
                    && assignmentDueAt != null && !now.isBefore(assignmentDueAt)));
    }

    public UUID getId() { return id; }
    public UUID getQuizId() { return quizId; }
    public UUID getAssignmentId() { return assignmentId; }
    public UUID getUserId() { return userId; }
    public AttemptStatus getStatus() { return status; }
    public int getAttemptNumber() { return attemptNumber; }
    public AnswerReleasePolicy getAnswerReleasePolicy() { return answerReleasePolicy; }
    public Instant getAssignmentDueAt() { return assignmentDueAt; }
    public Instant getStartedAt() { return startedAt; }
    public Instant getExpiresAt() { return expiresAt; }
    public Instant getSubmittedAt() { return submittedAt; }
    public boolean isTimedOut() { return timedOut; }
    public boolean isShowScore() { return showScore; }
    public boolean isAllowReview() { return allowReview; }
    public BigDecimal getScore() { return score; }
    public BigDecimal getMaxScore() { return maxScore; }
    public BigDecimal getPercentage() { return percentage; }
    public Integer getCorrectCount() { return correctCount; }
    public int getTotalQuestions() { return totalQuestions; }
    public String getSubmissionKey() { return submissionKey; }
    public long getVersion() { return version; }
}
