package com.genquiz.bk.job;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class JobStateTest {
    @Test
    void keepsGenerationCheckpointForRetryAndClearsItOnSuccess() {
        Job job = new Job(JobType.QUIZ_GENERATION, UUID.randomUUID(), UUID.randomUUID(), "{}",
                "checkpoint-test", 3, Instant.parse("2026-07-25T00:00:00Z"));

        job.checkpoint("{\"contractVersion\":2}", Instant.parse("2026-07-25T00:00:01Z"));
        assertEquals("{\"contractVersion\":2}", job.getCheckpointPayload());
        job.succeed("{}", Instant.parse("2026-07-25T00:00:02Z"));
        assertNull(job.getCheckpointPayload());
    }


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

    @Test
    void deferredPollIsNotRecordedAsAProcessingFailure() {
        Instant now = Instant.parse("2026-07-11T00:00:00Z");
        Job job = new Job(JobType.RAG_INDEX_POLL, UUID.randomUUID(), UUID.randomUUID(), "{}", null, 120, now);

        job.claim("worker-1", now);
        job.defer(now.plusSeconds(1), Duration.ofSeconds(2));

        assertEquals(JobStatus.RETRY, job.getStatus());
        assertEquals(0, job.getAttempts());
        assertEquals(null, job.getErrorCode());
        assertEquals(null, job.getErrorMessage());
    }

    @Test
    void preservesUpstreamRequestIdForActionableErrors() {
        Instant now = Instant.parse("2026-07-11T00:00:00Z");
        Job job = new Job(JobType.QUIZ_GENERATION, UUID.randomUUID(), UUID.randomUUID(), "{}", null, 1, now);

        job.claim("worker-1", now);
        job.fail("RAG_INDEX_INCONSISTENT", "Chỉ mục không nhất quán", now.plusSeconds(1),
                null, true, "rag-request-123");

        assertEquals(JobStatus.FAILED, job.getStatus());
        assertEquals("rag-request-123", job.getUpstreamRequestId());
        assertEquals("rag-request-123", JobDtos.Response.from(job).upstreamRequestId());
    }

    @Test
    void ownerRetryResetsFailureMetadataAndAttemptBudget() {
        Instant now = Instant.parse("2026-07-11T00:00:00Z");
        Job job = new Job(JobType.QUIZ_GENERATION, UUID.randomUUID(), UUID.randomUUID(), "{}", null, 1, now);
        job.claim("worker-1", now);
        job.fail("GROUNDED_QUIZ_INVALID", "AI trả sai cấu trúc", now.plusSeconds(1),
                null, true, "rag-request-123");

        job.retryByOwner(now.plusSeconds(2));

        assertEquals(JobStatus.RETRY, job.getStatus());
        assertEquals(0, job.getAttempts());
        assertEquals(null, job.getErrorCode());
        assertEquals(null, job.getUpstreamRequestId());
    }
}
