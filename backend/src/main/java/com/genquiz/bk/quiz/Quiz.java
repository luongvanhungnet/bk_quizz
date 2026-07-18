package com.genquiz.bk.quiz;

import com.genquiz.bk.topic.Visibility;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;
import java.util.UUID;
import com.genquiz.bk.common.ModerationStatus;

@Entity
@Table(name = "quizzes")
public class Quiz {
    @Id
    private UUID id;

    @Column(name = "topic_id", nullable = false, updatable = false)
    private UUID topicId;

    @Column(name = "owner_id", nullable = false, updatable = false)
    private UUID ownerId;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(columnDefinition = "text")
    private String description;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private QuizStatus status;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Visibility visibility;

    @Enumerated(EnumType.STRING)
    @Column(name = "moderation_status", nullable = false, length = 20)
    private ModerationStatus moderationStatus = ModerationStatus.ACTIVE;

    @Enumerated(EnumType.STRING)
    @Column(name = "generation_mode", nullable = false, length = 20)
    private GenerationMode generationMode;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Difficulty difficulty;

    @Column(name = "duration_minutes", nullable = false)
    private int durationMinutes;

    @Column(name = "error_code", length = 80)
    private String errorCode;

    @Column(name = "error_message", length = 1000)
    private String errorMessage;

    @Column(name = "published_at")
    private Instant publishedAt;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected Quiz() {}

    public static Quiz manual(UUID topicId, UUID ownerId, String title, String description,
                              Difficulty difficulty, int durationMinutes, Visibility visibility) {
        return create(topicId, ownerId, title, description, difficulty, durationMinutes, visibility,
                GenerationMode.MANUAL, QuizStatus.DRAFT);
    }

    public static Quiz generated(UUID topicId, UUID ownerId, String title, Difficulty difficulty,
                                 int durationMinutes, Visibility visibility) {
        return create(topicId, ownerId, title, null, difficulty, durationMinutes, visibility,
                GenerationMode.AI, QuizStatus.QUEUED);
    }

    private static Quiz create(UUID topicId, UUID ownerId, String title, String description,
                               Difficulty difficulty, int durationMinutes, Visibility visibility,
                               GenerationMode mode, QuizStatus status) {
        Quiz quiz = new Quiz();
        quiz.id = UUID.randomUUID();
        quiz.topicId = topicId;
        quiz.ownerId = ownerId;
        quiz.title = title.trim();
        quiz.description = description == null ? null : description.trim();
        quiz.difficulty = difficulty == null ? Difficulty.MIXED : difficulty;
        quiz.durationMinutes = durationMinutes;
        quiz.visibility = visibility == null ? Visibility.PRIVATE : visibility;
        quiz.generationMode = mode;
        quiz.status = status;
        quiz.createdAt = Instant.now();
        quiz.updatedAt = quiz.createdAt;
        return quiz;
    }

    public void update(String title, String description, Difficulty difficulty,
                       int durationMinutes, Visibility visibility) {
        if (status == QuizStatus.GENERATING) {
            throw new IllegalStateException("Không thể chỉnh sửa bài kiểm tra đang được tạo");
        }
        this.title = title.trim();
        this.description = description == null ? null : description.trim();
        this.difficulty = difficulty;
        this.durationMinutes = durationMinutes;
        this.visibility = visibility;
        this.updatedAt = Instant.now();
    }

    public void markGenerating() {
        if (status != QuizStatus.QUEUED && status != QuizStatus.FAILED) {
            throw new IllegalStateException("Bài kiểm tra không thể bắt đầu sinh câu hỏi");
        }
        status = QuizStatus.GENERATING;
        errorCode = null;
        errorMessage = null;
        updatedAt = Instant.now();
    }

    public void markReady() {
        status = QuizStatus.READY;
        errorCode = null;
        errorMessage = null;
        updatedAt = Instant.now();
    }

    public void markFailed(String code, String message) {
        status = QuizStatus.FAILED;
        errorCode = code;
        errorMessage = message == null ? null : message.substring(0, Math.min(1000, message.length()));
        updatedAt = Instant.now();
    }

    public void queueRetry() {
        if (generationMode != GenerationMode.AI || status != QuizStatus.FAILED) {
            throw new IllegalStateException("Chỉ có thể thử lại bài kiểm tra AI đã thất bại");
        }
        status = QuizStatus.QUEUED;
        errorCode = null;
        errorMessage = null;
        updatedAt = Instant.now();
    }

    public void publish(Instant now) {
        if (status != QuizStatus.DRAFT && status != QuizStatus.READY) {
            throw new IllegalStateException("Bài kiểm tra chưa sẵn sàng để xuất bản");
        }
        status = QuizStatus.PUBLISHED;
        publishedAt = now;
        updatedAt = now;
    }

    public void softDelete() {
        deletedAt = Instant.now();
        status = QuizStatus.ARCHIVED;
        updatedAt = deletedAt;
    }

    public boolean isOwnedBy(UUID actorId) { return ownerId.equals(actorId); }
    public UUID getId() { return id; }
    public UUID getTopicId() { return topicId; }
    public UUID getOwnerId() { return ownerId; }
    public String getTitle() { return title; }
    public String getDescription() { return description; }
    public QuizStatus getStatus() { return status; }
    public Visibility getVisibility() { return visibility; }
    public ModerationStatus getModerationStatus() { return moderationStatus; }
    public GenerationMode getGenerationMode() { return generationMode; }
    public Difficulty getDifficulty() { return difficulty; }
    public int getDurationMinutes() { return durationMinutes; }
    public String getErrorCode() { return errorCode; }
    public String getErrorMessage() { return errorMessage; }
    public Instant getPublishedAt() { return publishedAt; }
    public Instant getDeletedAt() { return deletedAt; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public long getVersion() { return version; }
}
