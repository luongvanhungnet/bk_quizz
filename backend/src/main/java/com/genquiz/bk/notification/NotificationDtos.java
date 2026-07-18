package com.genquiz.bk.notification;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

public final class NotificationDtos {
    private NotificationDtos() {}

    public record Response(
            UUID id,
            String type,
            String title,
            String body,
            String relatedType,
            UUID relatedId,
            Map<String, Object> data,
            boolean emailRequired,
            Instant emailSentAt,
            Instant readAt,
            Instant expiresAt,
            Instant createdAt,
            long version
    ) {
        public static Response from(Notification notification) {
            return new Response(notification.getId(), notification.getType(), notification.getTitle(),
                    notification.getBody(), notification.getRelatedType(), notification.getRelatedId(),
                    notification.getData(), notification.isEmailRequired(), notification.getEmailSentAt(),
                    notification.getReadAt(), notification.getExpiresAt(), notification.getCreatedAt(),
                    notification.getVersion());
        }
    }

    public record UnreadCount(long count) {}
    public record MarkAllResult(int updated) {}
}
