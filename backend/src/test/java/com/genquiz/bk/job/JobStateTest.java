package com.genquiz.bk.job;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class JobStateTest {

    @Test
    void retriesThenFailsAtMaximumAttempts() {
        Instant now = Instant.parse("2026-07-11T00:00:00Z");
        Job job = new Job(JobType.QUIZ_GENERATION, UUID.randomUUID(), UUID.randomUUID(), "{}", null, 2, now);

        job.claim("worker-1", now);
        job.fail("AI_TIMEOUT", "Quá thời gian", now.plusSeconds(1));
        assertEquals(JobStatus.RETRY, job.getStatus());
        assertTrue(job.getAvailableAt().isAfter(now));

        Instant retryAt = job.getAvailableAt();
        job.claim("worker-2", retryAt);
        job.fail("AI_TIMEOUT", "Quá thời gian", retryAt.plusSeconds(1));
        assertEquals(JobStatus.FAILED, job.getStatus());
    }
}
