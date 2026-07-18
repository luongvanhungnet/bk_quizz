package com.genquiz.bk.notification;

import com.genquiz.bk.common.error.ApiException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

@Service
public class NotificationService {
    private final NotificationRepository notifications;

    public NotificationService(NotificationRepository notifications) {
        this.notifications = notifications;
    }

    @Transactional(readOnly = true)
    public Page<NotificationDtos.Response> list(UUID userId, boolean unreadOnly, int page, int limit) {
        return notifications.list(userId, unreadOnly, Instant.now(), PageRequest.of(page - 1, limit))
                .map(NotificationDtos.Response::from);
    }

    @Transactional(readOnly = true)
    public long unreadCount(UUID userId) {
        return notifications.countUnread(userId, Instant.now());
    }

    @Transactional
    public NotificationDtos.Response markRead(UUID userId, UUID notificationId) {
        Notification notification = notifications.findByIdAndUserId(notificationId, userId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "NOTIFICATION_NOT_FOUND",
                        "Không tìm thấy thông báo."));
        notification.markRead(Instant.now());
        return NotificationDtos.Response.from(notification);
    }

    @Transactional
    public int markAllRead(UUID userId) {
        return notifications.markAllRead(userId, Instant.now());
    }

    @Transactional
    public void create(UUID userId, String type, String title, String body, String relatedType, UUID relatedId,
                       Map<String, Object> data, String deduplicationKey, boolean emailRequired) {
        if (deduplicationKey != null
                && notifications.existsByUserIdAndDeduplicationKey(userId, deduplicationKey)) {
            return;
        }
        notifications.save(new Notification(userId, type, title, body, relatedType, relatedId, data,
                deduplicationKey, emailRequired, null, Instant.now()));
    }
}
