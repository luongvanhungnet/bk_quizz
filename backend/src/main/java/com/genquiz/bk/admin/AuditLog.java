package com.genquiz.bk.admin;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "audit_logs")
public class AuditLog {
    @Id private UUID id;
    @Column(name = "actor_user_id") private UUID actorUserId;
    @Column(nullable = false, length = 100) private String action;
    @Column(name = "target_type", nullable = false, length = 80) private String targetType;
    @Column(name = "target_id") private UUID targetId;
    @Column(nullable = false, length = 20) private String outcome;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "metadata", nullable = false, columnDefinition = "jsonb")
    private String detailsJson;
    @Column(name = "created_at", nullable = false) private Instant createdAt;
    protected AuditLog() {}
    public AuditLog(UUID actorUserId, String action, String targetType, String targetId, String detailsJson) {
        this.id = UUID.randomUUID(); this.actorUserId = actorUserId; this.action = action;
        this.targetType = targetType;
        this.targetId = targetId == null ? null : UUID.fromString(targetId);
        this.outcome = "SUCCESS";
        this.detailsJson = detailsJson;
    }
    @PrePersist void init() { if (createdAt == null) createdAt = Instant.now(); }
    public UUID getId() { return id; }
    public UUID getActorUserId() { return actorUserId; }
    public String getAction() { return action; }
    public String getTargetType() { return targetType; }
    public String getTargetId() { return targetId == null ? null : targetId.toString(); }
    public String getDetailsJson() { return detailsJson; }
    public Instant getCreatedAt() { return createdAt; }
}
