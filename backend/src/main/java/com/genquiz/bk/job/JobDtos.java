package com.genquiz.bk.job;

import java.time.Instant;
import java.util.UUID;

public final class JobDtos {
    private JobDtos() {}

    public record Response(
            UUID id,
            JobType type,
            JobStatus status,
            UUID resourceId,
            int attempts,
            int maxAttempts,
            int progress,
            String step,
            String resultPayload,
            String errorCode,
            String errorMessage,
            String upstreamRequestId,
            Instant availableAt,
            Instant createdAt,
            Instant updatedAt,
            Instant completedAt) {
        public static Response from(Job job) {
            return new Response(job.getId(), job.getType(), job.getStatus(), job.getResourceId(),
                    job.getAttempts(), job.getMaxAttempts(), job.getProgress(), job.getStep(),
                    job.getResultPayload(), job.getErrorCode(),
                    job.getErrorMessage(), job.getUpstreamRequestId(),
                    job.getAvailableAt(),
                    job.getCreatedAt(), job.getUpdatedAt(), job.getCompletedAt());
        }
    }
}
