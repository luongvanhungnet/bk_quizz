package com.genquiz.bk.chat;

import jakarta.persistence.*;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

@Entity
@Table(name = "chat_threads")
public class ChatThread {
    @Id private UUID id;
    @Column(name = "user_id", nullable = false, updatable = false) private UUID userId;
    @Column(name = "topic_id", updatable = false) private UUID topicId;
    @Column(name = "quiz_id", updatable = false) private UUID quizId;
    @Column(name = "attempt_id", updatable = false) private UUID attemptId;
    @Column(length = 255) private String title;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 20) private ChatThreadStatus status;
    @Column(name = "expires_at", nullable = false) private Instant expiresAt;
    @Column(name = "deleted_at") private Instant deletedAt;
    @Column(name = "created_at", nullable = false, updatable = false) private Instant createdAt;
    @Column(name = "updated_at", nullable = false) private Instant updatedAt;
    @Version @Column(nullable = false) private long version;

    protected ChatThread() {}

    public ChatThread(UUID userId, UUID topicId, UUID quizId, UUID attemptId, String title, Instant now) {
        if ((topicId == null ? 0 : 1) + (quizId == null ? 0 : 1) + (attemptId == null ? 0 : 1) != 1) {
            throw new IllegalArgumentException("Hội thoại phải gắn với đúng một ngữ cảnh");
        }
        this.id = UUID.randomUUID(); this.userId = userId; this.topicId = topicId; this.quizId = quizId;
        this.attemptId = attemptId; this.title = title == null ? null : title.trim();
        this.status = ChatThreadStatus.ACTIVE; this.createdAt = now; this.updatedAt = now;
        this.expiresAt = now.plus(90, ChronoUnit.DAYS);
    }

    public void touch(Instant now) { requireActive(now); updatedAt = now; expiresAt = now.plus(90, ChronoUnit.DAYS); }
    public void requireActive(Instant now) {
        if (status != ChatThreadStatus.ACTIVE || deletedAt != null || !now.isBefore(expiresAt))
            throw new IllegalStateException("Hội thoại đã hết hạn hoặc đã bị xóa");
    }
    public void softDelete(Instant now) { status = ChatThreadStatus.DELETED; deletedAt = now; updatedAt = now; }
    public boolean isOwnedBy(UUID actorId) { return userId.equals(actorId); }
    public UUID getId() { return id; } public UUID getUserId() { return userId; }
    public UUID getTopicId() { return topicId; } public UUID getQuizId() { return quizId; }
    public UUID getAttemptId() { return attemptId; } public String getTitle() { return title; }
    public ChatThreadStatus getStatus() { return status; } public Instant getExpiresAt() { return expiresAt; }
    public Instant getCreatedAt() { return createdAt; } public Instant getUpdatedAt() { return updatedAt; }
    public long getVersion() { return version; }
}
