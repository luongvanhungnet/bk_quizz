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
            Instant createdAt,
            Instant updatedAt,
            long version) {
        public static Response from(SourceDocument source) {
            return new Response(source.getId(), source.getTopicId(), source.getName(), source.getKind(),
                    source.getStatus(), source.getContentType(), source.getSizeBytes(), source.getErrorCode(),
                    source.getErrorMessage(), source.getCreatedAt(), source.getUpdatedAt(), source.getVersion());
        }
    }

    public record UploadResponse(Response source, UUID jobId) {}
}
