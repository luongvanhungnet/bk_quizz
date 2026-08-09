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
import org.springframework.data.domain.PageRequest;
import org.springframework.web.server.ResponseStatusException;

@Service
public class JobService {
    private final JobRepository jobs;
    private final JobEventService events;
    private final Clock clock;

    @Autowired
    public JobService(JobRepository jobs, JobEventService events) {
        this(jobs, events, Clock.systemUTC());
    }

    JobService(JobRepository jobs, Clock clock) {
        this(jobs, null, clock);
    }

    JobService(JobRepository jobs, JobEventService events, Clock clock) {
        this.jobs = jobs;
        this.events = events;
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
        Job created = jobs.save(new Job(
                type, actorId, resourceId, payload, idempotencyKey, maxAttempts,
                Instant.now(clock)));
        if (type == JobType.QUIZ_GENERATION) {
            event(created, JobEventLevel.INFO, "QUEUED",
                    "Yêu cầu sinh quiz đã được đưa vào hàng đợi.");
        }
        return created;
    }

    @Transactional(readOnly = true)
    public Job getOwned(UUID actorId, UUID jobId) {
        return jobs.findByIdAndSubjectUserId(jobId, actorId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Không tìm thấy tác vụ"));
    }

    @Transactional(readOnly = true)
    public Job latestOwnedQuizGeneration(UUID actorId, UUID quizId) {
        return jobs.findFirstByResourceIdAndSubjectUserIdAndTypeOrderByCreatedAtDesc(
                        quizId, actorId, JobType.QUIZ_GENERATION)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Không tìm thấy tác vụ sinh quiz"));
    }

    @Transactional(readOnly = true)
    public java.util.List<Job> ownedQuizGenerationHistory(
            UUID actorId, UUID quizId, int limit) {
        return jobs.findByResourceIdAndSubjectUserIdAndTypeOrderByCreatedAtDesc(
                quizId, actorId, JobType.QUIZ_GENERATION,
                PageRequest.of(0, Math.max(1, Math.min(50, limit))));
    }

    @Transactional(readOnly = true)
    public boolean hasActiveQuizGeneration(UUID quizId) {
        return jobs.existsByResourceIdAndTypeAndStatusIn(
                quizId,
                JobType.QUIZ_GENERATION,
                Set.of(JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRY));
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
        event(job, JobEventLevel.INFO, "RETRY_REQUESTED",
                "Người dùng đã yêu cầu thử lại quá trình sinh quiz.");
        return job;
    }

    @Transactional
    public Optional<Job> claimNext(String workerId) {
        Instant now = Instant.now(clock);
        Optional<Job> job = jobs.lockNextAvailable(now);
        job.ifPresent(value -> {
            value.claim(workerId, now);
            if (value.getType() == JobType.QUIZ_GENERATION) {
                event(value, JobEventLevel.INFO, "WORKER_STARTED",
                        "Bộ xử lý đã bắt đầu tạo quiz.");
            }
        });
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
        Job job = requireJob(jobId);
        job.succeed(resultPayload, Instant.now(clock));
        if (job.getType() == JobType.QUIZ_GENERATION) {
            event(job, JobEventLevel.SUCCESS, "SUCCEEDED",
                    "Quiz đã được tạo và lưu thành công.");
        }
    }

    @Transactional
    public void progress(UUID jobId, int progress, String step) {
        Job job = requireJob(jobId);
        boolean changed = job.getProgress() != progress
                || !java.util.Objects.equals(job.getStep(), step);
        job.progress(progress, step, Instant.now(clock));
        if (changed && job.getType() == JobType.QUIZ_GENERATION) {
            event(job, JobEventLevel.INFO, step, progressMessage(step));
        }
    }

    @Transactional
    public void checkpoint(UUID jobId, String checkpointPayload) {
        requireJob(jobId).checkpoint(checkpointPayload, Instant.now(clock));
    }

    @Transactional
    public void defer(UUID jobId, Duration delay) {
        Job job = requireJob(jobId);
        job.defer(Instant.now(clock), delay);
        if (job.getType() == JobType.QUIZ_GENERATION) {
            event(job, JobEventLevel.INFO, "WAITING_NEXT_BATCH",
                    "Đang chờ trước khi tiếp tục nhóm câu hỏi tiếp theo.");
        }
    }

    @Transactional
    public void fail(UUID jobId, String safeCode, String safeMessage) {
        Job job = requireJob(jobId);
        job.fail(safeCode, safeMessage, Instant.now(clock));
        recordFailure(job, safeCode, safeMessage);
    }

    @Transactional
    public void fail(UUID jobId, String safeCode, String safeMessage, Duration retryAfter, boolean permanent) {
        Job job = requireJob(jobId);
        job.fail(safeCode, safeMessage, Instant.now(clock), retryAfter, permanent);
        recordFailure(job, safeCode, safeMessage);
    }

    @Transactional
    public void fail(UUID jobId, String safeCode, String safeMessage, Duration retryAfter,
                     boolean permanent, String upstreamRequestId) {
        Job job = requireJob(jobId);
        job.fail(safeCode, safeMessage, Instant.now(clock), retryAfter,
                permanent, upstreamRequestId);
        recordFailure(job, safeCode, safeMessage);
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

    private void recordFailure(Job job, String code, String message) {
        if (job.getType() != JobType.QUIZ_GENERATION) return;
        if (job.getStatus() == JobStatus.RETRY) {
            String retryMessage = "INVALID_CITATION_QUOTE".equals(code)
                    ? "BKQuiz đã giữ các câu có nguồn hợp lệ và sẽ chỉ tạo lại phần còn thiếu."
                    : (message == null || message.isBlank() ? code : message)
                    + " Hệ thống sẽ tự động thử lại.";
            event(job, JobEventLevel.WARNING, "RETRY_SCHEDULED",
                    retryMessage);
        } else {
            event(job, JobEventLevel.ERROR, code,
                    message == null || message.isBlank()
                            ? "Không thể hoàn tất quá trình sinh quiz." : message);
        }
    }

    private void event(
            Job job, JobEventLevel level, String code, String message) {
        if (events == null) return;
        events.record(
                job.getId(), level, code, message, job.getProgress(),
                null, null, null, job.getUpstreamRequestId(), null);
    }

    private static String progressMessage(String step) {
        if (step == null) return "Đang xử lý yêu cầu sinh quiz.";
        if (step.startsWith("GENERATING_BATCH_")) return "Đang tạo một nhóm câu hỏi.";
        if (step.startsWith("WAITING_GEMINI_RETRY_")) {
            return "Dịch vụ AI gặp lỗi tạm thời, đang chờ tự động thử lại.";
        }
        if (step.startsWith("WAITING_RAG_RETRY_")) {
            return "Dịch vụ xử lý tài liệu tạm gián đoạn, đang chờ tự động thử lại.";
        }
        if (step.startsWith("WAITING_COGNITIVE_RETRY_")) {
            return "Các câu hỏi vừa sinh chưa đạt mức độ tư duy yêu cầu. BKQuiz sẽ tự điều chỉnh và thử lại.";
        }
        if (step.startsWith("WAITING_CITATION_RETRY_")) {
            return "Một số câu hỏi chưa có nguồn đủ chắc chắn. BKQuiz đã giữ các câu hợp lệ và sẽ thử lại phần còn thiếu.";
        }
        if (step.startsWith("WAITING_NEXT_BATCH_")) {
            return "Đã hoàn tất một nhóm và đang chờ nhóm tiếp theo.";
        }
        return switch (step) {
            case "RETRIEVING" -> "Đang chuẩn bị tài liệu và nguồn kiến thức.";
            case "VALIDATING_ALL_BATCHES" -> "Đang kiểm tra toàn bộ câu hỏi và trích dẫn.";
            case "COMMITTING" -> "Đang lưu câu hỏi vào hệ thống.";
            default -> "Trạng thái mới: " + step;
        };
    }

    public record DocumentQueueHealth(long queuedJobs, long oldestQueuedSeconds) {}
}
