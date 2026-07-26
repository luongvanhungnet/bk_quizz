package com.genquiz.bk.job;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Duration;
import java.time.Instant;

@Entity
@Table(name = "job_worker_heartbeats")
public class JobWorkerHeartbeat {
    @Id
    @Column(name = "worker_id", length = 160)
    private String workerId;

    @Column(name = "started_at", nullable = false, updatable = false)
    private Instant startedAt;

    @Column(name = "last_seen_at", nullable = false)
    private Instant lastSeenAt;

    protected JobWorkerHeartbeat() {}

    public JobWorkerHeartbeat(String workerId, Instant now) {
        this.workerId = workerId;
        this.startedAt = now;
        this.lastSeenAt = now;
    }

    public void touch(Instant now) {
        lastSeenAt = now;
    }

    public boolean isFresh(Instant now, Duration threshold) {
        return !lastSeenAt.isBefore(now.minus(threshold));
    }

    public String getWorkerId() { return workerId; }
    public Instant getStartedAt() { return startedAt; }
    public Instant getLastSeenAt() { return lastSeenAt; }
}
