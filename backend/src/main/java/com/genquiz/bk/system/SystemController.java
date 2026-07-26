package com.genquiz.bk.system;

import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.job.JobService;
import com.genquiz.bk.job.JobWorkerPresenceService;
import com.genquiz.bk.rag.RagProcessorHealthService;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class SystemController {
    private final JdbcTemplate jdbc;
    private final JobService jobs;
    private final JobWorkerPresenceService workers;
    private final RagProcessorHealthService ragHealth;

    public SystemController(JdbcTemplate jdbc, JobService jobs, JobWorkerPresenceService workers,
                            RagProcessorHealthService ragHealth) {
        this.jdbc = jdbc;
        this.jobs = jobs;
        this.workers = workers;
        this.ragHealth = ragHealth;
    }

    @GetMapping("/health")
    ResponseEntity<ApiEnvelope<Map<String, Object>>> health() {
        try {
            jdbc.queryForObject("select 1", Integer.class);
            var queue = jobs.documentQueueHealth();
            boolean springWorker = workers.isAvailable();
            var rag = ragHealth.snapshot();
            boolean processorAvailable = springWorker && rag.apiAvailable() && rag.workerAvailable();
            var data = new LinkedHashMap<String, Object>();
            data.put("status", processorAvailable || queue.queuedJobs() == 0 ? "healthy" : "degraded");
            data.put("database", "connected");
            data.put("documentProcessor", processorAvailable ? "up" : "down");
            data.put("springWorker", springWorker ? "up" : "down");
            data.put("ragApi", rag.apiAvailable() ? "up" : "down");
            data.put("ragWorker", rag.workerAvailable() ? "up" : "down");
            data.put("ragQueueLength", rag.queueLength());
            data.put("ragPendingJobs", rag.pendingJobs());
            data.put("ragOldestPendingSeconds", rag.oldestPendingSeconds());
            data.put("queuedDocumentJobs", queue.queuedJobs());
            data.put("oldestQueuedSeconds", queue.oldestQueuedSeconds());
            data.put("timestamp", Instant.now());
            return ResponseEntity.ok(ApiEnvelope.success("Dịch vụ BKQuiz đang hoạt động.", data));
        } catch (RuntimeException exception) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(ApiEnvelope.success(
                    "Dịch vụ BKQuiz tạm thời không khả dụng.", Map.of(
                            "status", "unhealthy", "database", "disconnected", "timestamp", Instant.now())));
        }
    }
}
