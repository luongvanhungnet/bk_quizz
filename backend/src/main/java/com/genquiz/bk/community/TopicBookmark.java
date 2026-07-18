package com.genquiz.bk.community;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@IdClass(TopicBookmarkId.class)
@Table(name = "topic_bookmarks")
public class TopicBookmark {
    @Id @Column(name = "user_id", nullable = false, updatable = false)
    private UUID userId;
    @Id @Column(name = "topic_id", nullable = false, updatable = false)
    private UUID topicId;
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected TopicBookmark() {}
    public TopicBookmark(UUID userId, UUID topicId, Instant createdAt) {
        this.userId = userId; this.topicId = topicId; this.createdAt = createdAt;
    }
    public UUID getUserId() { return userId; }
    public UUID getTopicId() { return topicId; }
    public Instant getCreatedAt() { return createdAt; }
}

