package com.genquiz.bk.notification;

import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.common.api.PageMetadata;
import com.genquiz.bk.common.error.ApiException;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.data.domain.Page;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@Validated
@RestController
@RequestMapping("/api/notifications")
public class NotificationController {
    private final NotificationService service;

    public NotificationController(NotificationService service) {
        this.service = service;
    }

    @GetMapping
    public ApiEnvelope<List<NotificationDtos.Response>> list(
            @RequestParam(defaultValue = "false") boolean unreadOnly,
            @RequestParam(defaultValue = "1") @Min(1) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,
            Authentication authentication) {
        Page<NotificationDtos.Response> result = service.list(actor(authentication), unreadOnly, page, limit);
        return ApiEnvelope.page("Lấy danh sách thông báo thành công.", result.getContent(), metadata(result, page, limit));
    }

    @GetMapping("/unread-count")
    public ApiEnvelope<NotificationDtos.UnreadCount> unreadCount(Authentication authentication) {
        return ApiEnvelope.success("Lấy số thông báo chưa đọc thành công.",
                new NotificationDtos.UnreadCount(service.unreadCount(actor(authentication))));
    }

    @PatchMapping("/{notificationId}/read")
    public ApiEnvelope<NotificationDtos.Response> markRead(@PathVariable UUID notificationId,
                                                            Authentication authentication) {
        return ApiEnvelope.success("Đã đánh dấu thông báo là đã đọc.",
                service.markRead(actor(authentication), notificationId));
    }

    @PatchMapping("/read-all")
    public ApiEnvelope<NotificationDtos.MarkAllResult> markAllRead(Authentication authentication) {
        return ApiEnvelope.success("Đã đánh dấu tất cả thông báo là đã đọc.",
                new NotificationDtos.MarkAllResult(service.markAllRead(actor(authentication))));
    }

    private static UUID actor(Authentication authentication) {
        if (authentication == null || authentication.getName() == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "AUTHENTICATION_REQUIRED", "Bạn cần đăng nhập.");
        }
        try {
            return UUID.fromString(authentication.getName());
        } catch (IllegalArgumentException exception) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_AUTHENTICATION", "Phiên đăng nhập không hợp lệ.");
        }
    }

    private static PageMetadata metadata(Page<?> result, int page, int limit) {
        return new PageMetadata(page, limit, result.getTotalElements(), result.getTotalPages(),
                result.hasNext(), result.hasPrevious());
    }
}
