package com.genquiz.bk.notification;

import com.genquiz.bk.common.error.ApiException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class NotificationServiceTest {
    @Mock NotificationRepository notifications;

    @Test
    void userCanMarkOnlyOwnNotificationAsRead() {
        UUID ownerId = UUID.randomUUID();
        UUID notificationId = UUID.randomUUID();
        Notification notification = new Notification(ownerId, "ASSIGNMENT_PUBLISHED", "Bài mới", "Mở bài",
                "ASSIGNMENT", UUID.randomUUID(), Map.of(), null, false, null, Instant.now());
        when(notifications.findByIdAndUserId(notificationId, ownerId)).thenReturn(Optional.of(notification));

        NotificationDtos.Response response = new NotificationService(notifications).markRead(ownerId, notificationId);

        assertNotNull(response.readAt());
    }

    @Test
    void foreignNotificationLooksNotFound() {
        UUID userId = UUID.randomUUID();
        UUID notificationId = UUID.randomUUID();
        when(notifications.findByIdAndUserId(notificationId, userId)).thenReturn(Optional.empty());

        ApiException error = assertThrows(ApiException.class,
                () -> new NotificationService(notifications).markRead(userId, notificationId));

        assertEquals("NOTIFICATION_NOT_FOUND", error.code());
    }
}
