package com.genquiz.bk.job;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "jobs")
public class Job {
    @Id
    private UUID id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 40)
    private JobType type;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private JobStatus status;

    @Column(name = "subject_user_id", nullable = false, updatable = false)
    private UUID subjectUserId;

    @Column(name = "resource_id")
    private UUID resourceId;

    @Column(name = "idempotency_key", length = 200, unique = true)
    private String idempotencyKey;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private String payload;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "result_payload", columnDefinition = "jsonb")
    private String resultPayload;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "checkpoint_payload", columnDefinition = "jsonb")
    private String checkpointPayload;

    @Column(nullable = false)
    private int attempts;

    @Column(name = "max_attempts", nullable = false)
    private int maxAttempts;

    @Column(name = "available_at", nullable = false)
    private Instant availableAt;

    @Column(name = "locked_at")
    private Instant lockedAt;

    @Column(name = "locked_by", length = 120)
    private String lockedBy;

    @Column(name = "heartbeat_at")
    private Instant heartbeatAt;

    @Column(name = "error_code", length = 80)
    private String errorCode;

    @Column(name = "error_message", length = 1000)
    private String errorMessage;

    @Column(name = "upstream_request_id", length = 100)
    private String upstreamRequestId;
    @Column(name = "progress_percent", nullable = false) private int progress;
    @Column(name = "current_step", length = 64) private String step;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Column(name = "completed_at")
    private Instant completedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected Job() {}

    public Job(JobType type, UUID subjectUserId, UUID resourceId, String payload,
               String idempotencyKey, int maxAttempts, Instant now) {
        this.id = UUID.randomUUID();
        this.type = type;
        this.status = JobStatus.QUEUED;
        this.subjectUserId = subjectUserId;
        this.resourceId = resourceId;
        this.payload = payload == null || payload.isBlank() ? "{}" : payload;
        this.idempotencyKey = idempotencyKey == null || idempotencyKey.isBlank() ? null : idempotencyKey;
        this.maxAttempts = Math.max(1, maxAttempts);
        this.availableAt = now;
        this.createdAt = now;
        this.updatedAt = now;
        this.step = "QUEUED";
    }

    public void claim(String workerId, Instant now) {
        if (status != JobStatus.QUEUED && status != JobStatus.RETRY) {
            throw new IllegalStateException("Job không ở trạng thái có thể nhận");
        }
        status = JobStatus.RUNNING;
        attempts++;
        lockedBy = workerId;
        lockedAt = now;
        heartbeatAt = now;
        updatedAt = now;
    }

    public void heartbeat(String workerId, Instant now) {
        if (status != JobStatus.RUNNING || !workerId.equals(lockedBy)) {
            throw new IllegalStateException("Worker không sở hữu job này");
        }
        heartbeatAt = now;
        updatedAt = now;
    }

    public void succeed(String resultPayload, Instant now) {
        status = JobStatus.SUCCEEDED;
        this.resultPayload = resultPayload;
        errorCode = null;
        errorMessage = null;
        completedAt = now;
        updatedAt = now;
        progress = 100; step = "SUCCEEDED";
        checkpointPayload = null;
        clearLease();
        scrubSensitivePayload();
    }

    public void fail(String safeCode, String safeMessage, Instant now) {
        fail(safeCode, safeMessage, now, null, false);
    }

    public void fail(String safeCode, String safeMessage, Instant now, Duration retryAfter, boolean permanent) {
        fail(safeCode, safeMessage, now, retryAfter, permanent, null);
    }

    public void fail(String safeCode, String safeMessage, Instant now, Duration retryAfter,
                     boolean permanent, String requestId) {
        errorCode = safeCode;
        errorMessage = safeMessage == null ? null : safeMessage.substring(0, Math.min(1000, safeMessage.length()));
        upstreamRequestId = requestId == null || requestId.isBlank()
                ? null : requestId.substring(0, Math.min(100, requestId.length()));
        updatedAt = now;
        if (permanent || attempts >= maxAttempts) {
            status = JobStatus.FAILED;
            completedAt = now;
            scrubSensitivePayload();
        } else {
            status = JobStatus.RETRY;
            Duration delay = retryAfter == null
                    ? Duration.ofSeconds(Math.min(300, 1L << Math.min(8, Math.max(0, attempts - 1))))
                    : retryAfter;
            availableAt = now.plus(delay.isNegative() ? Duration.ZERO : delay);
        }
        clearLease();
    }

    public void defer(Instant now, Duration delay) {
        status = JobStatus.RETRY;
        attempts = Math.max(0, attempts - 1);
        availableAt = now.plus(delay == null || delay.isNegative() ? Duration.ZERO : delay);
        errorCode = null;
        errorMessage = null;
        updatedAt = now;
        clearLease();
    }

    public void reclaimIfStale(Instant now) {
        status = JobStatus.RETRY;
        availableAt = now;
        updatedAt = now;
        clearLease();
    }

    public void retryByAdmin(Instant now) {
        if (status != JobStatus.FAILED) throw new IllegalStateException("Chỉ có thể thử lại job đã thất bại");
        status = JobStatus.RETRY; availableAt = now; completedAt = null; errorCode = null; errorMessage = null; updatedAt = now; clearLease();
    }

    public void retryByOwner(Instant now) {
        if (status != JobStatus.FAILED || type != JobType.QUIZ_GENERATION) {
            throw new IllegalStateException("Chỉ có thể thử lại job sinh quiz đã thất bại");
        }
        status = JobStatus.RETRY;
        attempts = 0;
        availableAt = now;
        completedAt = null;
        errorCode = null;
        errorMessage = null;
        upstreamRequestId = null;
        progress = 0;
        step = "QUEUED";
        updatedAt = now;
        clearLease();
    }

    public void cancelByAdmin(Instant now) {
        if (status != JobStatus.QUEUED && status != JobStatus.RETRY) throw new IllegalStateException("Không thể hủy job ở trạng thái hiện tại");
        status = JobStatus.FAILED; errorCode = "CANCELLED_BY_ADMIN"; errorMessage = "Job đã bị quản trị viên hủy."; completedAt = now; updatedAt = now; clearLease(); scrubSensitivePayload();
    }

    private void clearLease() {
        lockedAt = null;
        lockedBy = null;
        heartbeatAt = null;
    }

    private void scrubSensitivePayload() {
        if (type == JobType.AUTH_EMAIL) payload = "{}";
    }

    public UUID getId() { return id; }
    public JobType getType() { return type; }
    public JobStatus getStatus() { return status; }
    public UUID getSubjectUserId() { return subjectUserId; }
    public UUID getResourceId() { return resourceId; }
    public String getPayload() { return payload; }
    public String getResultPayload() { return resultPayload; }
    public String getCheckpointPayload() { return checkpointPayload; }
    public int getAttempts() { return attempts; }
    public int getMaxAttempts() { return maxAttempts; }
    public Instant getAvailableAt() { return availableAt; }
    public Instant getHeartbeatAt() { return heartbeatAt; }
    public String getErrorCode() { return errorCode; }
    public String getErrorMessage() { return errorMessage; }
    public String getUpstreamRequestId() { return upstreamRequestId; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Instant getCompletedAt() { return completedAt; }
    public int getProgress() { return progress; }
    public String getStep() { return step; }
    public void checkpoint(String value, Instant now) {
        checkpointPayload = value;
        updatedAt = now;
    }
    public void progress(int value, String currentStep, Instant now) {
        progress = Math.max(0, Math.min(100, value)); step = currentStep; updatedAt = now;
    }
}
