package com.genquiz.bk.community;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

import java.time.Instant;
import java.util.UUID;

@Entity
@IdClass(BookmarkId.class)
@Table(name = "bookmarks")
public class Bookmark {
    @Id
    @Column(name = "user_id", nullable = false, updatable = false)
    private UUID userId;

    @Id
    @Column(name = "quiz_id", nullable = false, updatable = false)
    private UUID quizId;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected Bookmark() {}

    public Bookmark(UUID userId, UUID quizId, Instant now) {
        this.userId = userId;
        this.quizId = quizId;
        this.createdAt = now;
    }

    public UUID getUserId() { return userId; }
    public UUID getQuizId() { return quizId; }
    public Instant getCreatedAt() { return createdAt; }
}
