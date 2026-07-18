package com.genquiz.bk.job;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class JobService {
    private final JobRepository jobs;
    private final Clock clock;

    @Autowired
    public JobService(JobRepository jobs) {
        this(jobs, Clock.systemUTC());
    }

    JobService(JobRepository jobs, Clock clock) {
        this.jobs = jobs;
        this.clock = clock;
    }

    @Transactional
    public Job enqueue(JobType type, UUID actorId, UUID resourceId, String payload,
                       String idempotencyKey, int maxAttempts) {
        if (idempotencyKey != null && !idempotencyKey.isBlank()) {
            Optional<Job> existing = jobs.findByIdempotencyKey(idempotencyKey);
            if (existing.isPresent()) {
                if (!existing.get().getSubjectUserId().equals(actorId) || existing.get().getType() != type) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "Khóa idempotency đã được sử dụng");
                }
                return existing.get();
            }
        }
        return jobs.save(new Job(type, actorId, resourceId, payload, idempotencyKey, maxAttempts,
                Instant.now(clock)));
    }

    @Transactional(readOnly = true)
    public Job getOwned(UUID actorId, UUID jobId) {
        return jobs.findByIdAndSubjectUserId(jobId, actorId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Không tìm thấy tác vụ"));
    }

    @Transactional
    public Optional<Job> claimNext(String workerId) {
        Instant now = Instant.now(clock);
        Optional<Job> job = jobs.lockNextAvailable(now);
        job.ifPresent(value -> value.claim(workerId, now));
        return job;
    }

    @Transactional
    public void heartbeat(UUID jobId, String workerId) {
        Job job = jobs.findById(jobId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Không tìm thấy tác vụ"));
        job.heartbeat(workerId, Instant.now(clock));
    }

    @Transactional
    public void succeed(UUID jobId, String resultPayload) {
        requireJob(jobId).succeed(resultPayload, Instant.now(clock));
    }

    @Transactional
    public void fail(UUID jobId, String safeCode, String safeMessage) {
        requireJob(jobId).fail(safeCode, safeMessage, Instant.now(clock));
    }

    @Transactional
    public void fail(UUID jobId, String safeCode, String safeMessage, Duration retryAfter, boolean permanent) {
        requireJob(jobId).fail(safeCode, safeMessage, Instant.now(clock), retryAfter, permanent);
    }

    @Transactional
    public int reclaimStale(Duration leaseTimeout) {
        Instant now = Instant.now(clock);
        var staleJobs = jobs.findStaleRunning(now.minus(leaseTimeout));
        staleJobs.forEach(job -> job.reclaimIfStale(now));
        return staleJobs.size();
    }

    private Job requireJob(UUID jobId) {
        return jobs.findById(jobId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Không tìm thấy tác vụ"));
    }
}
