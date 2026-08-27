package com.genquiz.bk.chat;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class AttemptAiChatDtos {
    private AttemptAiChatDtos() {}

    public record SendRequest(
            @NotNull UUID snapshotId,
            @NotNull UUID clientMessageId,
            @NotBlank @Size(min = 2, max = 4000) String message) {}

    public record Citation(
            UUID sourceChunkId, UUID sourceDocumentId, String filename,
            Integer pageNumber, Integer slideNumber, int chunkIndex,
            String heading, String evidenceQuote) {}

    public record Message(
            UUID id, UUID questionSnapshotId, String role, String status,
            String content, String model, String errorCode, String errorMessage,
            UUID replyToMessageId, Instant createdAt, Instant completedAt,
            List<Citation> citations) {}

    public record History(List<Message> items, UUID nextCursor, boolean hasMore) {}
}
