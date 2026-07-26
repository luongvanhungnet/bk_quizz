package com.genquiz.bk.job;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class JobWorkerHeartbeatTest {

    @Test
    void heartbeatExpiresAfterConfiguredThreshold() {
        Instant now = Instant.parse("2026-07-23T10:00:00Z");
        JobWorkerHeartbeat heartbeat = new JobWorkerHeartbeat("worker-1", now);

        assertTrue(heartbeat.isFresh(now.plusSeconds(29), Duration.ofSeconds(30)));
        assertFalse(heartbeat.isFresh(now.plusSeconds(31), Duration.ofSeconds(30)));
    }
}
