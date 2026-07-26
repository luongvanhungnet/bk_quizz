package com.genquiz.bk.rag;

import com.genquiz.bk.config.RagProperties;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

@Service
public class RagProcessorHealthService {
    private static final Logger log = LoggerFactory.getLogger(RagProcessorHealthService.class);

    private final RagClient rag;
    private final RagProperties properties;
    private volatile Snapshot snapshot = Snapshot.unavailable();

    public RagProcessorHealthService(RagClient rag, RagProperties properties) {
        this.rag = rag;
        this.properties = properties;
    }

    @Scheduled(fixedDelayString = "${bkquiz.rag.health-poll-delay:10s}", initialDelayString = "0")
    public void refresh() {
        if (!properties.enabled()) {
            snapshot = new Snapshot(false, false, 0, 0, 0, Instant.now());
            return;
        }
        try {
            RagDtos.Health health = rag.health();
            boolean workerUp = "UP".equals(health.checks().get("celeryWorker"));
            snapshot = new Snapshot(
                    true, workerUp, health.queueLength(), health.pendingJobs(),
                    health.oldestPendingSeconds(), Instant.now());
            if (!workerUp && (health.queueLength() > 0 || health.pendingJobs() > 0)) {
                log.warn("RAG worker unavailable queueLength={} pendingJobs={} oldestPendingSeconds={}",
                        health.queueLength(), health.pendingJobs(), health.oldestPendingSeconds());
            }
        } catch (RuntimeException exception) {
            snapshot = Snapshot.unavailable();
            log.warn("RAG API health check failed error={}", exception.getClass().getSimpleName());
        }
    }

    public Snapshot snapshot() {
        return snapshot;
    }

    public record Snapshot(boolean apiAvailable, boolean workerAvailable, int queueLength,
                           int pendingJobs, long oldestPendingSeconds, Instant checkedAt) {
        static Snapshot unavailable() {
            return new Snapshot(false, false, 0, 0, 0, Instant.now());
        }
    }
}
