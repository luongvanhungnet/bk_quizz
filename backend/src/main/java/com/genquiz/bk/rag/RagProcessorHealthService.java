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
            snapshot = Snapshot.unavailable();
            return;
        }
        try {
            RagDtos.Health health = rag.health();
            boolean workerUp = "UP".equals(health.checks().get("celeryWorker"));
            RagDtos.Capabilities capabilities;
            try {
                capabilities = rag.capabilities();
            } catch (RuntimeException exception) {
                capabilities = new RagDtos.Capabilities(
                        "unavailable", java.util.Map.of(), "unknown");
            }
            boolean contractCompatible = RagDtos.QUIZ_GENERATION_CONTRACT.equals(
                    capabilities.quizGenerationContract())
                    && requiredCapabilitiesAvailable(capabilities.capabilities());
            snapshot = new Snapshot(
                    true, workerUp, health.queueLength(), health.pendingJobs(),
                    health.oldestPendingSeconds(), contractCompatible,
                    capabilities.quizGenerationContract(), capabilities.buildRevision(),
                    Instant.now());
            if (!contractCompatible) {
                log.warn(
                        "RAG quiz contract mismatch expected={} actual={} buildRevision={}",
                        RagDtos.QUIZ_GENERATION_CONTRACT,
                        capabilities.quizGenerationContract(),
                        capabilities.buildRevision());
            }
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

    private static boolean requiredCapabilitiesAvailable(
            java.util.Map<String, Boolean> capabilities) {
        return capabilities != null && java.util.List.of(
                        "questionPlan", "acceptedQuestions", "streaming",
                        "partialCognitiveRepair")
                .stream()
                .allMatch(name -> Boolean.TRUE.equals(capabilities.get(name)));
    }

    public record Snapshot(boolean apiAvailable, boolean workerAvailable, int queueLength,
                           int pendingJobs, long oldestPendingSeconds,
                           boolean quizGenerationContractCompatible,
                           String quizGenerationContract,
                           String buildRevision,
                           Instant checkedAt) {
        static Snapshot unavailable() {
            return new Snapshot(
                    false, false, 0, 0, 0, false,
                    "unavailable", "unknown", Instant.now());
        }
    }
}
