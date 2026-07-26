package com.genquiz.bk.job;

import com.genquiz.bk.config.AppProperties;
import com.genquiz.bk.config.RagProperties;
import com.genquiz.bk.config.QuizGenerationBatchProperties;
import com.genquiz.bk.source.SourceService;
import com.genquiz.bk.quiz.QuizService;
import com.genquiz.bk.rag.RagServiceException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.dao.DataIntegrityViolationException;

import java.net.InetAddress;
import java.time.Duration;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import jakarta.annotation.PostConstruct;

@Component
@ConditionalOnProperty(name = "bkquiz.jobs.worker-enabled", havingValue = "true")
public class JobWorker {
    private static final Logger log = LoggerFactory.getLogger(JobWorker.class);
    private final JobService jobs;
    private final Map<JobType, JobHandler> handlers = new EnumMap<>(JobType.class);
    private final AppProperties properties;
    private final SourceService sources;
    private final QuizService quizzes;
    private final JobWorkerPresenceService presence;
    private final RagProperties ragProperties;
    private final QuizGenerationBatchProperties quizBatchProperties;
    private final String workerId;

    public JobWorker(JobService jobs, List<JobHandler> handlers, AppProperties properties,
                     SourceService sources, QuizService quizzes,
                     JobWorkerPresenceService presence, RagProperties ragProperties,
                     QuizGenerationBatchProperties quizBatchProperties) {
        this.jobs = jobs; this.properties = properties; this.sources = sources; this.quizzes = quizzes;
        this.presence = presence; this.ragProperties = ragProperties;
        this.quizBatchProperties = quizBatchProperties;
        handlers.forEach(handler -> this.handlers.put(handler.type(), handler));
        this.workerId = hostname() + "-" + ProcessHandle.current().pid();
    }

    @PostConstruct
    void started() {
        presence.heartbeat(workerId);
        log.info("BKQuiz job worker ENABLED workerId={} pollDelay={} ragUrl={}",
                workerId, properties.jobs().pollDelay(), ragProperties.baseUrl());
    }

    @Scheduled(fixedDelayString = "${bkquiz.jobs.heartbeat-delay:10s}")
    public void heartbeat() {
        try {
            presence.heartbeat(workerId);
        } catch (RuntimeException exception) {
            log.error("Không thể cập nhật heartbeat cho job worker {}.", workerId, exception);
        }
    }

    @Scheduled(fixedDelayString = "${bkquiz.jobs.poll-delay:1s}")
    public void poll() {
        jobs.claimNext(workerId).ifPresent(this::process);
    }

    @Scheduled(fixedDelayString = "30s")
    public void reclaimStale() {
        int count = jobs.reclaimStale(properties.jobs().leaseDuration());
        if (count > 0) log.warn("Đã thu hồi {} job bị mất heartbeat.", count);
    }

    private void process(Job job) {
        String previousTraceId = MDC.get("traceId");
        MDC.put("traceId", "job-" + job.getId());
        try {
            processWithTrace(job);
        } finally {
            if (previousTraceId == null) MDC.remove("traceId");
            else MDC.put("traceId", previousTraceId);
        }
    }

    private void processWithTrace(Job job) {
        JobHandler handler = handlers.get(job.getType());
        try {
            if (handler == null) throw new IllegalStateException("Chưa có handler cho loại job " + job.getType());
            jobs.succeed(job.getId(), handler.handle(job));
        } catch (JobDeferredException deferred) {
            jobs.defer(job.getId(), deferred.delay());
            log.debug("Job {} đang chờ tác vụ upstream hoàn tất.", job.getId());
        } catch (Exception exception) {
            log.error("Job {} loại {} thất bại ở lần {}.", job.getId(), job.getType(), job.getAttempts(), exception);
            if (exception instanceof RagServiceException rag && rag.upstreamRequestId() != null) {
                log.error("RAG upstream requestId={} cho job {}.", rag.upstreamRequestId(), job.getId());
            }
            String code = safeCode(job.getType(), exception);
            String message = safeMessage(job.getType(), exception);
            boolean terminal = job.getAttempts() >= job.getMaxAttempts()
                    || exception instanceof NonRetryableJobException
                    || isPermanentFailure(job.getType(), exception)
                    || (exception instanceof RagServiceException rag && !rag.retryable());
            if ((job.getType() == JobType.SOURCE_INGESTION || job.getType() == JobType.RAG_INDEX_POLL)
                    && terminal) {
                sources.markFailed(job.getResourceId(), code, message);
            }
            if (job.getType() == JobType.QUIZ_GENERATION && terminal) {
                quizzes.markFailed(job.getResourceId(), code, message);
            }
            if (exception instanceof NonRetryableJobException
                    || isPermanentFailure(job.getType(), exception)) {
                jobs.fail(job.getId(), code, message, null, true);
            } else if (exception instanceof RagServiceException rag) {
                jobs.fail(job.getId(), rag.code(), rag.getMessage(),
                        retryDelay(job.getType(), rag.retryAfter()),
                        !rag.retryable(), rag.upstreamRequestId());
            } else if (exception instanceof RetryableJobException retryable) {
                jobs.fail(job.getId(), code, message,
                        retryable.retryAfter(), false);
            } else {
                jobs.fail(job.getId(), code, message);
            }
        }
    }

    private String safeCode(JobType type, Exception exception) {
        if (exception instanceof RagServiceException rag) return rag.code();
        String classified = failureCode(type, exception);
        if (!"JOB_PROCESSING_FAILED".equals(classified)) return classified;
        if (exception instanceof IllegalArgumentException && "SOURCE_NOT_INDEXED".equals(exception.getMessage()))
            return "SOURCE_NOT_INDEXED";
        return exception instanceof IllegalArgumentException ? "INVALID_JOB_INPUT" : "JOB_PROCESSING_FAILED";
    }
    private String safeMessage(JobType type, Exception exception) {
        if (exception instanceof RagServiceException rag && rag.getMessage() != null && !rag.getMessage().isBlank()) {
            return rag.getMessage();
        }
        return switch (safeCode(type, exception)) {
            case "QUESTION_DIFFICULTY_INVALID" -> "Độ khó của câu hỏi không hợp lệ.";
            case "QUIZ_PERSISTENCE_FAILED" -> "Backend không thể lưu quiz do dữ liệu không thỏa ràng buộc.";
            case "SOURCE_NOT_INDEXED" -> "Một hoặc nhiều tài liệu chưa được lập chỉ mục RAG.";
            case "RAG_CONTEXT_INSUFFICIENT" -> "Tài liệu không có đủ thông tin để sinh quiz.";
            case "RAG_INDEX_INCONSISTENT" -> "Chỉ mục tài liệu không nhất quán. Vui lòng lập chỉ mục lại.";
            case "RAG_DOCUMENT_TEXT_INSUFFICIENT" -> "Tài liệu có quá ít nội dung hữu ích để sinh quiz.";
            case "GROUNDED_QUIZ_INVALID" -> "AI không tạo được quiz có nguồn trích dẫn hợp lệ.";
            case "RAG_RATE_LIMITED" -> "Dịch vụ AI đang giới hạn yêu cầu. Vui lòng thử lại sau.";
            case "RAG_UNAVAILABLE" -> "Không thể kết nối dịch vụ RAG.";
            default -> "Không thể hoàn tất tác vụ. Vui lòng thử lại.";
        };
    }
    private String hostname() {
        try { return InetAddress.getLocalHost().getHostName(); }
        catch (Exception ignored) { return "worker"; }
    }

    static String failureCode(JobType type, Exception exception) {
        if (type == JobType.QUIZ_GENERATION && exception instanceof DataIntegrityViolationException) {
            return "QUIZ_PERSISTENCE_FAILED";
        }
        if (type == JobType.QUIZ_GENERATION && exception instanceof IllegalArgumentException
                && "QUESTION_DIFFICULTY_INVALID".equals(exception.getMessage())) {
            return "QUESTION_DIFFICULTY_INVALID";
        }
        return "JOB_PROCESSING_FAILED";
    }

    static boolean isPermanentFailure(JobType type, Exception exception) {
        return type == JobType.QUIZ_GENERATION
                && (exception instanceof DataIntegrityViolationException
                || (exception instanceof IllegalArgumentException
                && "QUESTION_DIFFICULTY_INVALID".equals(exception.getMessage())));
    }

    Duration retryDelay(JobType type, Duration upstreamDelay) {
        return retryDelay(type, upstreamDelay, quizBatchProperties.batchRetryDelay());
    }

    static Duration retryDelay(
            JobType type, Duration upstreamDelay, Duration minimum) {
        if (type != JobType.QUIZ_GENERATION) return upstreamDelay;
        if (upstreamDelay == null || upstreamDelay.compareTo(minimum) < 0) {
            return minimum;
        }
        return upstreamDelay;
    }
}
