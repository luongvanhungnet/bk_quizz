package com.genquiz.bk.classroom;

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
@Table(name = "classrooms")
public class Classroom {
    @Id
    private UUID id;

    @Column(name = "owner_id", nullable = false, updatable = false)
    private UUID ownerId;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(columnDefinition = "text")
    private String description;

    @Column(name = "join_code", nullable = false, columnDefinition = "citext")
    private String joinCode;

    @Column(name = "join_enabled", nullable = false)
    private boolean joinEnabled = true;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ClassroomStatus status;

    @Enumerated(EnumType.STRING)
    @Column(name = "moderation_status", nullable = false, length = 20)
    private ModerationStatus moderationStatus = ModerationStatus.ACTIVE;

    @Column(name = "archived_at")
    private Instant archivedAt;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected Classroom() {}

    public Classroom(UUID ownerId, String name, String description, String joinCode, Instant now) {
        this.id = UUID.randomUUID();
        this.ownerId = ownerId;
        this.name = name.trim();
        this.description = normalize(description);
        this.joinCode = joinCode;
        this.status = ClassroomStatus.ACTIVE;
        this.createdAt = now;
        this.updatedAt = now;
    }

    public void update(String name, String description, Instant now) {
        requireActive();
        this.name = name.trim();
        this.description = normalize(description);
        this.updatedAt = now;
    }

    public void archive(Instant now) {
        if (status == ClassroomStatus.ARCHIVED) return;
        status = ClassroomStatus.ARCHIVED;
        archivedAt = now;
        updatedAt = now;
    }

    public void rotateJoinCode(String value, Instant now) { requireActive(); joinCode = value; updatedAt = now; }
    public void setJoinEnabled(boolean value, Instant now) { requireActive(); joinEnabled = value; updatedAt = now; }

    public void requireActive() {
        if (status != ClassroomStatus.ACTIVE || deletedAt != null) {
            throw new IllegalStateException("Lớp học đã được lưu trữ.");
        }
    }

    private static String normalize(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    public boolean isOwnedBy(UUID userId) { return ownerId.equals(userId); }
    public UUID getId() { return id; }
    public UUID getOwnerId() { return ownerId; }
    public String getName() { return name; }
    public String getDescription() { return description; }
    public String getJoinCode() { return joinCode; }
    public boolean isJoinEnabled() { return joinEnabled; }
    public ClassroomStatus getStatus() { return status; }
    public ModerationStatus getModerationStatus() { return moderationStatus; }
    public Instant getArchivedAt() { return archivedAt; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Instant getDeletedAt() { return deletedAt; }
    public long getVersion() { return version; }
}
