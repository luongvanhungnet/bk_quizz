package com.genquiz.bk.job;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "job_events")
public class JobEvent {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "job_id", nullable = false, updatable = false)
    private UUID jobId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 12)
    private JobEventLevel level;

    @Column(nullable = false, length = 80)
    private String code;

    @Column(nullable = false, length = 1000)
    private String message;

    @Column
    private Integer progress;

    @Column(length = 40)
    private String provider;

    @Column(name = "batch_index")
    private Integer batchIndex;

    @Column(name = "part_index")
    private Integer partIndex;

    @Column(name = "request_id", length = 100)
    private String requestId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private String metadata;

    @Column(name = "occurred_at", nullable = false, updatable = false)
    private Instant occurredAt;

    protected JobEvent() {}

    public JobEvent(
            UUID jobId,
            JobEventLevel level,
            String code,
            String message,
            Integer progress,
            String provider,
            Integer batchIndex,
            Integer partIndex,
            String requestId,
            String metadata,
            Instant occurredAt) {
        this.jobId = jobId;
        this.level = level;
        this.code = limit(code, 80);
        this.message = limit(message, 1000);
        this.progress = progress == null ? null : Math.max(0, Math.min(100, progress));
        this.provider = limitNullable(provider, 40);
        this.batchIndex = batchIndex;
        this.partIndex = partIndex;
        this.requestId = limitNullable(requestId, 100);
        this.metadata = metadata == null || metadata.isBlank() ? "{}" : metadata;
        this.occurredAt = occurredAt;
    }

    private static String limit(String value, int max) {
        String safe = value == null || value.isBlank() ? "STATUS" : value;
        return safe.substring(0, Math.min(max, safe.length()));
    }

    private static String limitNullable(String value, int max) {
        return value == null || value.isBlank()
                ? null
                : value.substring(0, Math.min(max, value.length()));
    }

    public Long getId() { return id; }
    public UUID getJobId() { return jobId; }
    public JobEventLevel getLevel() { return level; }
    public String getCode() { return code; }
    public String getMessage() { return message; }
    public Integer getProgress() { return progress; }
    public String getProvider() { return provider; }
    public Integer getBatchIndex() { return batchIndex; }
    public Integer getPartIndex() { return partIndex; }
    public String getRequestId() { return requestId; }
    public String getMetadata() { return metadata; }
    public Instant getOccurredAt() { return occurredAt; }
}
