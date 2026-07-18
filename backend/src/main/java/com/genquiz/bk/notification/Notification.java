package com.genquiz.bk.notification;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

@Entity
@Table(name = "notifications")
public class Notification {
    @Id
    private UUID id;

    @Column(name = "user_id", nullable = false, updatable = false)
    private UUID userId;

    @Column(nullable = false, length = 80)
    private String type;

    @Column(nullable = false, length = 255)
    private String title;

    @Column(nullable = false, columnDefinition = "text")
    private String body;

    @Column(name = "related_type", length = 80)
    private String relatedType;

    @Column(name = "related_id")
    private UUID relatedId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> data;

    @Column(name = "deduplication_key", length = 200)
    private String deduplicationKey;

    @Column(name = "email_required", nullable = false)
    private boolean emailRequired;

    @Column(name = "email_sent_at")
    private Instant emailSentAt;

    @Column(name = "read_at")
    private Instant readAt;

    @Column(name = "expires_at")
    private Instant expiresAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected Notification() {}

    public Notification(UUID userId, String type, String title, String body, String relatedType, UUID relatedId,
                        Map<String, Object> data, String deduplicationKey, boolean emailRequired,
                        Instant expiresAt, Instant now) {
        this.id = UUID.randomUUID();
        this.userId = userId;
        this.type = type.trim();
        this.title = title.trim();
        this.body = body.trim();
        this.relatedType = normalize(relatedType);
        this.relatedId = relatedId;
        this.data = data == null ? new LinkedHashMap<>() : new LinkedHashMap<>(data);
        this.deduplicationKey = normalize(deduplicationKey);
        this.emailRequired = emailRequired;
        this.expiresAt = expiresAt;
        this.createdAt = now;
        this.updatedAt = now;
    }

    public void markRead(Instant now) {
        if (readAt != null) return;
        readAt = now;
        updatedAt = now;
    }

    private static String normalize(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    public UUID getId() { return id; }
    public UUID getUserId() { return userId; }
    public String getType() { return type; }
    public String getTitle() { return title; }
    public String getBody() { return body; }
    public String getRelatedType() { return relatedType; }
    public UUID getRelatedId() { return relatedId; }
    public Map<String, Object> getData() {
        return Collections.unmodifiableMap(new LinkedHashMap<>(data));
    }
    public boolean isEmailRequired() { return emailRequired; }
    public Instant getEmailSentAt() { return emailSentAt; }
    public Instant getReadAt() { return readAt; }
    public Instant getExpiresAt() { return expiresAt; }
    public Instant getCreatedAt() { return createdAt; }
    public long getVersion() { return version; }
}
