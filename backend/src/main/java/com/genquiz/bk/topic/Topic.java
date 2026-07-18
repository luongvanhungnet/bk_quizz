package com.genquiz.bk.topic;

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
@Table(name = "topics")
public class Topic {
    @Id
    private UUID id;

    @Column(name = "owner_id", nullable = false, updatable = false)
    private UUID ownerId;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(columnDefinition = "text")
    private String description;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Visibility visibility;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private TopicStatus status;

    @Enumerated(EnumType.STRING)
    @Column(name = "moderation_status", nullable = false, length = 20)
    private ModerationStatus moderationStatus = ModerationStatus.ACTIVE;

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

    protected Topic() {}

    public Topic(UUID ownerId, String title, String description, Visibility visibility) {
        this.id = UUID.randomUUID();
        this.ownerId = ownerId;
        this.title = title.trim();
        this.description = description == null ? null : description.trim();
        this.visibility = visibility == null ? Visibility.PRIVATE : visibility;
        this.status = TopicStatus.DRAFT;
        this.createdAt = Instant.now();
        this.updatedAt = this.createdAt;
    }

    public void update(String title, String description, Visibility visibility) {
        this.title = title.trim();
        this.description = description == null ? null : description.trim();
        this.visibility = visibility == null ? this.visibility : visibility;
        this.updatedAt = Instant.now();
    }

    public void publish(Instant now) {
        this.status = TopicStatus.PUBLISHED;
        this.publishedAt = now;
        this.updatedAt = now;
    }

    public void archive() {
        this.status = TopicStatus.ARCHIVED;
        this.updatedAt = Instant.now();
    }

    public void softDelete() {
        this.deletedAt = Instant.now();
        this.updatedAt = this.deletedAt;
    }

    public boolean isOwnedBy(UUID actorId) { return ownerId.equals(actorId); }
    public boolean isPubliclyVisible() {
        return deletedAt == null && moderationStatus == ModerationStatus.ACTIVE && status == TopicStatus.PUBLISHED && visibility == Visibility.PUBLIC;
    }

    public UUID getId() { return id; }
    public UUID getOwnerId() { return ownerId; }
    public String getTitle() { return title; }
    public String getDescription() { return description; }
    public Visibility getVisibility() { return visibility; }
    public TopicStatus getStatus() { return status; }
    public ModerationStatus getModerationStatus() { return moderationStatus; }
    public Instant getPublishedAt() { return publishedAt; }
    public Instant getDeletedAt() { return deletedAt; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public long getVersion() { return version; }
}
