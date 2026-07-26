package com.genquiz.bk.job;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import java.util.Set;
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
    public Job retryOwnedQuizGeneration(UUID actorId, UUID quizId) {
        Job job = jobs.findFirstByResourceIdAndSubjectUserIdAndTypeOrderByCreatedAtDesc(
                        quizId, actorId, JobType.QUIZ_GENERATION)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Không tìm thấy tác vụ sinh quiz"));
        try {
            job.retryByOwner(Instant.now(clock));
        } catch (IllegalStateException exception) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, exception.getMessage());
        }
        return job;
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
    public void progress(UUID jobId, int progress, String step) {
        requireJob(jobId).progress(progress, step, Instant.now(clock));
    }

    @Transactional
    public void checkpoint(UUID jobId, String checkpointPayload) {
        requireJob(jobId).checkpoint(checkpointPayload, Instant.now(clock));
    }

    @Transactional
    public void defer(UUID jobId, Duration delay) {
        requireJob(jobId).defer(Instant.now(clock), delay);
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
    public void fail(UUID jobId, String safeCode, String safeMessage, Duration retryAfter,
                     boolean permanent, String upstreamRequestId) {
        requireJob(jobId).fail(safeCode, safeMessage, Instant.now(clock), retryAfter,
                permanent, upstreamRequestId);
    }

    @Transactional
    public int reclaimStale(Duration leaseTimeout) {
        Instant now = Instant.now(clock);
        var staleJobs = jobs.findStaleRunning(now.minus(leaseTimeout));
        staleJobs.forEach(job -> job.reclaimIfStale(now));
        return staleJobs.size();
    }

    @Transactional(readOnly = true)
    public DocumentQueueHealth documentQueueHealth() {
        Set<JobType> types = Set.of(JobType.SOURCE_INGESTION, JobType.RAG_INDEX_POLL);
        Set<JobStatus> statuses = Set.of(JobStatus.QUEUED, JobStatus.RETRY);
        long queued = jobs.countByTypesAndStatuses(types, statuses);
        Instant oldest = jobs.findOldestCreatedAt(types, statuses);
        long oldestSeconds = oldest == null ? 0
                : Math.max(0, Duration.between(oldest, Instant.now(clock)).toSeconds());
        return new DocumentQueueHealth(queued, oldestSeconds);
    }

    private Job requireJob(UUID jobId) {
        return jobs.findById(jobId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Không tìm thấy tác vụ"));
    }

    public record DocumentQueueHealth(long queuedJobs, long oldestQueuedSeconds) {}
}
