package com.genquiz.bk.topic;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.UUID;

public final class TopicDtos {
    private TopicDtos() {}

    public record SaveRequest(
            @NotBlank(message = "Tiêu đề không được để trống")
            @Size(max = 200, message = "Tiêu đề tối đa 200 ký tự") String title,
            @Size(max = 5000, message = "Mô tả tối đa 5000 ký tự") String description,
            Visibility visibility) {}

    public record Response(
            UUID id,
            UUID ownerId,
            String title,
            String description,
            Visibility visibility,
            TopicStatus status,
            Instant publishedAt,
            Instant createdAt,
            Instant updatedAt,
            long version) {
        public static Response from(Topic topic) {
            return new Response(topic.getId(), topic.getOwnerId(), topic.getTitle(), topic.getDescription(),
                    topic.getVisibility(), topic.getStatus(), topic.getPublishedAt(), topic.getCreatedAt(),
                    topic.getUpdatedAt(), topic.getVersion());
        }
    }
}
