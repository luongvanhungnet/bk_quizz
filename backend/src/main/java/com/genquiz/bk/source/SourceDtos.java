package com.genquiz.bk.source;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.UUID;

public final class SourceDtos {
    private SourceDtos() {}

    public record PasteRequest(
            @NotBlank(message = "Tên tài liệu không được để trống")
            @Size(max = 255, message = "Tên tài liệu tối đa 255 ký tự") String name,
            @NotBlank(message = "Nội dung không được để trống")
            @Size(min = 100, message = "Nội dung phải có ít nhất 100 ký tự") String text) {}

    public record Response(
            UUID id,
            UUID topicId,
            String name,
            SourceKind kind,
            SourceStatus status,
            String contentType,
            Long sizeBytes,
            String errorCode,
            String errorMessage,
            int indexingProgress,
            String indexingStep,
            String processingStage,
            boolean processingDelayed,
            boolean processorAvailable,
            Instant indexingProgressAt,
            Integer pageCount,
            int chunkCount,
            Instant indexedAt,
            Instant createdAt,
            Instant updatedAt,
            long version) {
        public static Response from(SourceDocument source, boolean processorAvailable, Instant now) {
            boolean processing = source.getStatus() != SourceStatus.READY
                    && source.getStatus() != SourceStatus.FAILED
                    && source.getStatus() != SourceStatus.DELETED;
            boolean delayed = processing && source.getIndexingProgressAt().isBefore(now.minusSeconds(30));
            return new Response(source.getId(), source.getTopicId(), source.getName(), source.getKind(),
                    source.getStatus(), source.getContentType(), source.getSizeBytes(), source.getErrorCode(),
                    source.getErrorMessage(), source.getIndexingProgress(), source.getIndexingStep(),
                    stage(source), delayed, processorAvailable,
                    source.getIndexingProgressAt(),
                    source.getPageCount(), source.getChunkCount(), source.getIndexedAt(),
                    source.getCreatedAt(), source.getUpdatedAt(), source.getVersion());
        }

        private static String stage(SourceDocument source) {
            if (source.getStatus() == SourceStatus.READY) return "READY";
            if (source.getStatus() == SourceStatus.FAILED) return "FAILED";
            if (source.getStatus() == SourceStatus.DELETED) return "DELETED";
            String step = source.getIndexingStep();
            if (step == null || step.isBlank()) {
                return source.getStatus() == SourceStatus.UPLOADED ? "QUEUED" : source.getStatus().name();
            }
            return switch (step) {
                case "PENDING" -> "QUEUED";
                case "VALIDATING", "SCANNING" -> "VALIDATING";
                case "PARSING", "EXTRACTING" -> "PARSING";
                case "CHUNKING" -> "CHUNKING";
                case "EMBEDDING" -> "EMBEDDING";
                case "COMMITTING", "SYNCING" -> "SYNCING";
                case "SUCCEEDED" -> "READY";
                case "FAILED" -> "FAILED";
                default -> step;
            };
        }
    }

    public record UploadResponse(Response source, UUID jobId) {}
}
