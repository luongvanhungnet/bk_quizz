package com.genquiz.bk.classroom;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.persistence.Version;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "classroom_members", uniqueConstraints = {
        @UniqueConstraint(name = "uq_classroom_members_classroom_user", columnNames = {"classroom_id", "user_id"})
})
public class ClassroomMember {
    @Id
    private UUID id;

    @Column(name = "classroom_id", nullable = false, updatable = false)
    private UUID classroomId;

    @Column(name = "user_id", nullable = false, updatable = false)
    private UUID userId;

    @Enumerated(EnumType.STRING)
    @Column(name = "member_role", nullable = false, length = 20)
    private ClassroomMemberRole role;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ClassroomMemberStatus status;

    @Column(name = "joined_at", nullable = false)
    private Instant joinedAt;

    @Column(name = "left_at")
    private Instant leftAt;

    @Column(name = "last_read_message_at")
    private Instant lastReadMessageAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected ClassroomMember() {}

    public ClassroomMember(UUID classroomId, UUID userId, ClassroomMemberRole role, Instant now) {
        this.id = UUID.randomUUID();
        this.classroomId = classroomId;
        this.userId = userId;
        this.role = role;
        this.status = ClassroomMemberStatus.ACTIVE;
        this.joinedAt = now;
        this.createdAt = now;
        this.updatedAt = now;
    }

    public void reactivate(ClassroomMemberRole role, Instant now) {
        this.role = role;
        this.status = ClassroomMemberStatus.ACTIVE;
        this.joinedAt = now;
        this.leftAt = null;
        this.updatedAt = now;
    }

    public void leave(Instant now) { endMembership(ClassroomMemberStatus.LEFT, now); }
    public void remove(Instant now) { endMembership(ClassroomMemberStatus.REMOVED, now); }
    public void markRead(Instant now) { lastReadMessageAt = now; updatedAt = now; }
    public void changeRole(ClassroomMemberRole value, Instant now) { role = value; updatedAt = now; }

    private void endMembership(ClassroomMemberStatus target, Instant now) {
        if (status != ClassroomMemberStatus.ACTIVE) return;
        status = target;
        leftAt = now;
        updatedAt = now;
    }

    public boolean isActive() { return status == ClassroomMemberStatus.ACTIVE; }
    public boolean isTeacher() { return isActive() && role == ClassroomMemberRole.TEACHER; }
    public UUID getId() { return id; }
    public UUID getClassroomId() { return classroomId; }
    public UUID getUserId() { return userId; }
    public ClassroomMemberRole getRole() { return role; }
    public ClassroomMemberStatus getStatus() { return status; }
    public Instant getJoinedAt() { return joinedAt; }
    public Instant getLeftAt() { return leftAt; }
    public Instant getLastReadMessageAt() { return lastReadMessageAt; }
    public long getVersion() { return version; }
}
