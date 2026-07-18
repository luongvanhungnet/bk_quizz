package com.genquiz.bk.community;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "ratings")
public class Rating {
    @Id
    private UUID id;

    @Column(name = "user_id", nullable = false, updatable = false)
    private UUID userId;

    @Column(name = "quiz_id", nullable = false, updatable = false)
    private UUID quizId;

    @Column(name = "attempt_id", nullable = false)
    private UUID attemptId;

    @Column(nullable = false)
    private short rating;

    @Column(columnDefinition = "text")
    private String review;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected Rating() {}

    public Rating(UUID userId, UUID quizId, UUID attemptId, int rating, String review, Instant now) {
        this.id = UUID.randomUUID();
        this.userId = userId;
        this.quizId = quizId;
        this.createdAt = now;
        apply(attemptId, rating, review, now);
    }

    public void update(UUID attemptId, int rating, String review, Instant now) {
        apply(attemptId, rating, review, now);
    }

    private void apply(UUID attemptId, int rating, String review, Instant now) {
        if (rating < 1 || rating > 5) throw new IllegalArgumentException("Điểm đánh giá phải từ 1 đến 5.");
        this.attemptId = attemptId;
        this.rating = (short) rating;
        this.review = review == null || review.isBlank() ? null : review.trim();
        this.updatedAt = now;
        this.deletedAt = null;
    }

    public void softDelete(Instant now) {
        if (deletedAt != null) return;
        deletedAt = now;
        updatedAt = now;
    }

    public UUID getId() { return id; }
    public UUID getUserId() { return userId; }
    public UUID getQuizId() { return quizId; }
    public UUID getAttemptId() { return attemptId; }
    public short getRating() { return rating; }
    public String getReview() { return review; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Instant getDeletedAt() { return deletedAt; }
    public long getVersion() { return version; }
}
