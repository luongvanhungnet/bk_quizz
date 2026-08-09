package com.genquiz.bk.job;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

public final class JobEventDtos {
    private JobEventDtos() {}

    @JsonInclude(JsonInclude.Include.ALWAYS)
    public record Item(
            long id,
            UUID jobId,
            Instant occurredAt,
            JobEventLevel level,
            String code,
            String message,
            Integer progress,
            String provider,
            Integer batchIndex,
            Integer partIndex,
            String requestId,
            JsonNode metadata) {
        static Item from(JobEvent event, ObjectMapper mapper) {
            JsonNode metadata;
            try {
                metadata = mapper.readTree(event.getMetadata());
            } catch (Exception ignored) {
                metadata = mapper.createObjectNode();
            }
            return new Item(
                    event.getId(),
                    event.getJobId(),
                    event.getOccurredAt(),
                    event.getLevel(),
                    event.getCode(),
                    event.getMessage(),
                    event.getProgress(),
                    event.getProvider(),
                    event.getBatchIndex(),
                    event.getPartIndex(),
                    event.getRequestId(),
                    metadata);
        }
    }

    public record Page(List<Item> items, long nextCursor, boolean hasMore) {}
}
