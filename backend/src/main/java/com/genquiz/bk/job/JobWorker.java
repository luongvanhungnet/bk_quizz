package com.genquiz.bk.job;

import com.genquiz.bk.config.AppProperties;
import com.genquiz.bk.source.SourceService;
import com.genquiz.bk.quiz.QuizService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.net.InetAddress;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

@Component
@ConditionalOnProperty(name = "bkquiz.jobs.worker-enabled", havingValue = "true")
public class JobWorker {
    private static final Logger log = LoggerFactory.getLogger(JobWorker.class);
    private final JobService jobs;
    private final Map<JobType, JobHandler> handlers = new EnumMap<>(JobType.class);
    private final AppProperties properties;
    private final SourceService sources;
    private final QuizService quizzes;
    private final String workerId;

    public JobWorker(JobService jobs, List<JobHandler> handlers, AppProperties properties,
                     SourceService sources, QuizService quizzes) {
        this.jobs = jobs; this.properties = properties; this.sources = sources; this.quizzes = quizzes;
        handlers.forEach(handler -> this.handlers.put(handler.type(), handler));
        this.workerId = hostname() + "-" + ProcessHandle.current().pid();
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
        JobHandler handler = handlers.get(job.getType());
        try {
            if (handler == null) throw new IllegalStateException("Chưa có handler cho loại job " + job.getType());
            jobs.succeed(job.getId(), handler.handle(job));
        } catch (Exception exception) {
            log.error("Job {} loại {} thất bại ở lần {}.", job.getId(), job.getType(), job.getAttempts(), exception);
            if (job.getType() == JobType.SOURCE_INGESTION && job.getAttempts() >= job.getMaxAttempts()) {
                sources.markFailed(job.getResourceId(), safeCode(exception),
                        "Không thể trích xuất nội dung tài liệu.");
            }
            if (job.getType() == JobType.QUIZ_GENERATION && job.getAttempts() >= job.getMaxAttempts()) {
                quizzes.markFailed(job.getResourceId(), safeCode(exception),
                        "Không thể sinh câu hỏi hợp lệ từ tài liệu.");
            }
            if (exception instanceof NonRetryableJobException) {
                jobs.fail(job.getId(), safeCode(exception), "Tác vụ không thể thử lại do lỗi cấu hình.", null, true);
            } else if (exception instanceof RetryableJobException retryable) {
                jobs.fail(job.getId(), safeCode(exception), "Dịch vụ tạm thời không khả dụng.",
                        retryable.retryAfter(), false);
            } else {
                jobs.fail(job.getId(), safeCode(exception), "Không thể hoàn tất tác vụ. Vui lòng thử lại.");
            }
        }
    }

    private String safeCode(Exception exception) {
        return exception instanceof IllegalArgumentException ? "INVALID_JOB_INPUT" : "JOB_PROCESSING_FAILED";
    }
    private String hostname() {
        try { return InetAddress.getLocalHost().getHostName(); }
        catch (Exception ignored) { return "worker"; }
    }
}
