package com.genquiz.bk.job;

import com.genquiz.bk.config.AppProperties;
import com.genquiz.bk.config.RagProperties;
import com.genquiz.bk.config.QuizGenerationBatchProperties;
import com.genquiz.bk.source.SourceService;
import com.genquiz.bk.quiz.QuizService;
import com.genquiz.bk.quiz.QuizGenerationOperation;
import com.genquiz.bk.rag.RagServiceException;
import com.genquiz.bk.auth.ResendDeliveryException;
import com.genquiz.bk.auth.ResendConnectivityException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.web.server.ResponseStatusException;

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
            if (exception instanceof RagServiceException rag && rag.details() != null) {
                log.warn("RAG failure details jobId={} code={} fields={}",
                        job.getId(), rag.code(), safeRagDetailSummary(rag.details()));
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
            if (job.getType() == JobType.QUIZ_GENERATION
                    && terminal
                    && QuizGenerationOperation.fromPayload(job.getPayload())
                    != QuizGenerationOperation.APPEND) {
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
            case "COGNITIVE_CONSTRAINT_VIOLATION" -> "Một số câu hỏi AI chưa đáp ứng mức độ tư duy đã chọn.";
            case "GROUNDED_QUIZ_INVALID" -> "AI không tạo được quiz có nguồn trích dẫn hợp lệ.";
            case "INVALID_CITATION_QUOTE" -> "Một số câu hỏi chưa có nguồn trích dẫn đủ chắc chắn.";
            case "RAG_RATE_LIMITED" -> "Dịch vụ AI đang giới hạn yêu cầu. Vui lòng thử lại sau.";
            case "RAG_UNAVAILABLE" -> "Không thể kết nối dịch vụ RAG.";
            case "RAG_STREAM_READ_TIMEOUT" -> "RAG không gửi trạng thái mới trước thời hạn chờ của backend.";
            case "QUIZ_CITATION_SOURCE_FORBIDDEN" -> "Trích dẫn không thuộc nguồn đã chọn cho Quiz.";
            case "RAG_CONTRACT_MISMATCH" -> "Backend và dịch vụ RAG chưa dùng cùng contract sinh quiz.";
            case "RESEND_AUTHENTICATION_FAILED" -> "Khóa API Resend không hợp lệ hoặc đã bị thu hồi.";
            case "RESEND_SENDER_NOT_VERIFIED" -> "Tên miền gửi email chưa được xác minh trên Resend.";
            case "RESEND_SENDER_INVALID" -> "Địa chỉ người gửi email không hợp lệ.";
            case "RESEND_CONFIGURATION_MISSING" -> "Worker gửi email chưa được cấu hình Resend.";
            case "RESEND_REQUEST_REJECTED" -> "Resend từ chối yêu cầu gửi email.";
            case "RESEND_CONNECTION_TIMEOUT" -> "Kết nối từ máy chủ tới Resend đã quá thời gian chờ.";
            case "RESEND_CONNECTION_FAILED" -> "Máy chủ tạm thời không thể kết nối Resend.";
            default -> "Không thể hoàn tất tác vụ. Vui lòng thử lại.";
        };
    }
    private String hostname() {
        try { return InetAddress.getLocalHost().getHostName(); }
        catch (Exception ignored) { return "worker"; }
    }

    private static String safeRagDetailSummary(tools.jackson.databind.JsonNode details) {
        if (details.isArray()) {
            var values = new java.util.ArrayList<String>();
            for (tools.jackson.databind.JsonNode detail : details) {
                String field = detail.path("field").stringValue("");
                String type = detail.path("type").stringValue("");
                if (!field.isBlank() || !type.isBlank()) values.add(field + ":" + type);
            }
            return values.toString();
        }
        return "expected=" + details.path("expectedContract").stringValue("unknown")
                + ",actual=" + details.path("actualContract").stringValue("unknown")
                + ",build=" + details.path("actualBuildRevision").stringValue("unknown");
    }

    static String failureCode(JobType type, Exception exception) {
        if (exception instanceof ResendDeliveryException resend) {
            return resend.code();
        }
        if (exception instanceof ResendConnectivityException resend) {
            return resend.code();
        }
        if (type == JobType.QUIZ_GENERATION
                && exception instanceof ResponseStatusException response
                && response.getReason() != null
                && java.util.Set.of(
                        "QUIZ_CHANGED_DURING_GENERATION",
                        "QUIZ_QUESTION_LIMIT_EXCEEDED",
                        "DUPLICATE_QUESTION_PROMPT",
                        "QUIZ_CITATION_SOURCE_FORBIDDEN")
                .contains(response.getReason())) {
            return response.getReason();
        }
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
                || (exception instanceof ResponseStatusException response
                && response.getReason() != null
                && java.util.Set.of(
                        "QUIZ_CHANGED_DURING_GENERATION",
                        "QUIZ_QUESTION_LIMIT_EXCEEDED",
                        "DUPLICATE_QUESTION_PROMPT",
                        "QUIZ_CITATION_SOURCE_FORBIDDEN")
                .contains(response.getReason()))
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
