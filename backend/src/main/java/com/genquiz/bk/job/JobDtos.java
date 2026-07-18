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
            String resultPayload,
            String errorCode,
            String errorMessage,
            Instant createdAt,
            Instant updatedAt,
            Instant completedAt) {
        public static Response from(Job job) {
            return new Response(job.getId(), job.getType(), job.getStatus(), job.getResourceId(),
                    job.getAttempts(), job.getMaxAttempts(), job.getResultPayload(), job.getErrorCode(),
                    job.getErrorMessage(), job.getCreatedAt(), job.getUpdatedAt(), job.getCompletedAt());
        }
    }
}
