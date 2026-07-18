package com.genquiz.bk.community;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "quiz_statistics")
public class QuizStatistics {
    @Id
    @Column(name = "quiz_id")
    private UUID quizId;

    @Column(name = "learner_count", nullable = false)
    private long learnerCount;

    @Column(name = "attempt_count", nullable = false)
    private long attemptCount;

    @Column(name = "rating_count", nullable = false)
    private long ratingCount;

    @Column(name = "rating_sum", nullable = false)
    private long ratingSum;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected QuizStatistics() {}

    public QuizStatistics(UUID quizId) {
        this.quizId = quizId;
        this.updatedAt = Instant.now();
    }

    public void refresh(long learnerCount, long attemptCount, long ratingCount, long ratingSum, Instant now) {
        this.learnerCount = learnerCount;
        this.attemptCount = attemptCount;
        this.ratingCount = ratingCount;
        this.ratingSum = ratingSum;
        this.updatedAt = now;
    }

    public UUID getQuizId() { return quizId; }
    public long getLearnerCount() { return learnerCount; }
    public long getAttemptCount() { return attemptCount; }
    public long getRatingCount() { return ratingCount; }
    public long getRatingSum() { return ratingSum; }
    public Instant getUpdatedAt() { return updatedAt; }
    public long getVersion() { return version; }
}
