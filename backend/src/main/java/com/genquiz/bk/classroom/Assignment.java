package com.genquiz.bk.classroom;

import com.genquiz.bk.attempt.AnswerReleasePolicy;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "assignments")
public class Assignment {
    @Id
    private UUID id;

    @Column(name = "classroom_id", nullable = false, updatable = false)
    private UUID classroomId;

    @Column(name = "quiz_id", nullable = false, updatable = false)
    private UUID quizId;

    @Column(name = "created_by", nullable = false, updatable = false)
    private UUID createdBy;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(columnDefinition = "text")
    private String instructions;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private AssignmentStatus status;

    @Column(name = "opens_at")
    private Instant opensAt;

    @Column(name = "due_at")
    private Instant dueAt;

    @Column(name = "duration_minutes", nullable = false)
    private int durationMinutes;

    @Column(name = "max_attempts", nullable = false)
    private int maxAttempts;

    @Enumerated(EnumType.STRING)
    @Column(name = "answer_release_policy", nullable = false, length = 30)
    private AnswerReleasePolicy answerReleasePolicy;

    @Enumerated(EnumType.STRING) @Column(name = "share_kind", nullable = false, length = 30)
    private AssignmentShareKind shareKind = AssignmentShareKind.TEACHER_ASSIGNMENT;
    @Column(name = "show_score", nullable = false) private boolean showScore = true;
    @Column(name = "allow_review", nullable = false) private boolean allowReview = true;
    @Column(name = "shuffle_questions", nullable = false) private boolean shuffleQuestions;
    @Column(name = "shuffle_options", nullable = false) private boolean shuffleOptions;
    @Column(name = "show_leaderboard", nullable = false) private boolean showLeaderboard;

    @Column(name = "published_at")
    private Instant publishedAt;

    @Column(name = "closed_at")
    private Instant closedAt;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected Assignment() {}

    public Assignment(UUID classroomId, UUID quizId, UUID createdBy, String title, String instructions,
                      Instant opensAt, Instant dueAt, int durationMinutes, int maxAttempts,
                      AnswerReleasePolicy answerReleasePolicy, Instant now) {
        this.id = UUID.randomUUID();
        this.classroomId = classroomId;
        this.quizId = quizId;
        this.createdBy = createdBy;
        this.status = AssignmentStatus.DRAFT;
        apply(title, instructions, opensAt, dueAt, durationMinutes, maxAttempts, answerReleasePolicy);
        this.createdAt = now;
        this.updatedAt = now;
    }

    public void configureSharing(AssignmentShareKind kind, Boolean showScore, Boolean allowReview,
                                 Boolean shuffleQuestions, Boolean shuffleOptions, Boolean showLeaderboard) {
        this.shareKind = kind == null ? AssignmentShareKind.TEACHER_ASSIGNMENT : kind;
        this.showScore = showScore == null || showScore;
        this.allowReview = allowReview == null || allowReview;
        this.shuffleQuestions = Boolean.TRUE.equals(shuffleQuestions);
        this.shuffleOptions = Boolean.TRUE.equals(shuffleOptions);
        this.showLeaderboard = Boolean.TRUE.equals(showLeaderboard);
    }

    public void update(String title, String instructions, Instant opensAt, Instant dueAt,
                       int durationMinutes, int maxAttempts, AnswerReleasePolicy answerReleasePolicy, Instant now) {
        if (status != AssignmentStatus.DRAFT) {
            throw new IllegalStateException("Chỉ có thể chỉnh sửa bài tập ở trạng thái nháp.");
        }
        apply(title, instructions, opensAt, dueAt, durationMinutes, maxAttempts, answerReleasePolicy);
        updatedAt = now;
    }

    private void apply(String title, String instructions, Instant opensAt, Instant dueAt,
                       int durationMinutes, int maxAttempts, AnswerReleasePolicy answerReleasePolicy) {
        if (opensAt != null && dueAt != null && !dueAt.isAfter(opensAt)) {
            throw new IllegalArgumentException("Hạn nộp phải sau thời điểm mở bài.");
        }
        if (answerReleasePolicy == AnswerReleasePolicy.AFTER_DUE_DATE && dueAt == null) {
            throw new IllegalArgumentException("Chính sách công bố sau hạn nộp yêu cầu một hạn nộp cụ thể.");
        }
        this.title = title.trim();
        this.instructions = instructions == null || instructions.isBlank() ? null : instructions.trim();
        this.opensAt = opensAt;
        this.dueAt = dueAt;
        this.durationMinutes = durationMinutes;
        this.maxAttempts = maxAttempts;
        this.answerReleasePolicy = answerReleasePolicy;
    }

    public void publish(Instant now) {
        if (status != AssignmentStatus.DRAFT) {
            throw new IllegalStateException("Bài tập không còn ở trạng thái nháp.");
        }
        if (dueAt != null && !dueAt.isAfter(now)) {
            throw new IllegalStateException("Không thể xuất bản bài tập đã quá hạn.");
        }
        status = AssignmentStatus.PUBLISHED;
        publishedAt = now;
        updatedAt = now;
    }

    public void close(Instant now) {
        if (status != AssignmentStatus.PUBLISHED) {
            throw new IllegalStateException("Chỉ có thể đóng bài tập đang được giao.");
        }
        status = AssignmentStatus.CLOSED;
        closedAt = now;
        updatedAt = now;
    }

    public void softDelete(Instant now) {
        if (status != AssignmentStatus.DRAFT) {
            throw new IllegalStateException("Chỉ có thể xóa bài tập chưa xuất bản.");
        }
        deletedAt = now;
        updatedAt = now;
    }

    public UUID getId() { return id; }
    public UUID getClassroomId() { return classroomId; }
    public UUID getQuizId() { return quizId; }
    public UUID getCreatedBy() { return createdBy; }
    public String getTitle() { return title; }
    public String getInstructions() { return instructions; }
    public AssignmentStatus getStatus() { return status; }
    public Instant getOpensAt() { return opensAt; }
    public Instant getDueAt() { return dueAt; }
    public int getDurationMinutes() { return durationMinutes; }
    public int getMaxAttempts() { return maxAttempts; }
    public AnswerReleasePolicy getAnswerReleasePolicy() { return answerReleasePolicy; }
    public AssignmentShareKind getShareKind() { return shareKind; }
    public boolean isShowScore() { return showScore; }
    public boolean isAllowReview() { return allowReview; }
    public boolean isShuffleQuestions() { return shuffleQuestions; }
    public boolean isShuffleOptions() { return shuffleOptions; }
    public boolean isShowLeaderboard() { return showLeaderboard; }
    public Instant getPublishedAt() { return publishedAt; }
    public Instant getClosedAt() { return closedAt; }
    public Instant getDeletedAt() { return deletedAt; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public long getVersion() { return version; }
}
