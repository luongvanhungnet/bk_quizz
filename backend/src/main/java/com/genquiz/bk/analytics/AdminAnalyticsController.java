package com.genquiz.bk.analytics;

import com.genquiz.bk.common.api.ApiEnvelope;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/admin/analytics")
public class AdminAnalyticsController {
    private final AdminAnalyticsService service;
    public AdminAnalyticsController(AdminAnalyticsService service) { this.service=service; }

    @PreAuthorize("hasAuthority('analytics:read')")
    @GetMapping("/overview")
    ApiEnvelope<AdminAnalyticsDtos.Overview> overview(@RequestParam(required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate dateFrom,
                                                      @RequestParam(required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate dateTo) {
        return ApiEnvelope.success("Lấy tổng quan phân tích thành công.",service.overview(dateFrom,dateTo));
    }
    @PreAuthorize("hasAuthority('analytics:read')")
    @GetMapping("/users")
    ApiEnvelope<AdminAnalyticsDtos.UserAnalytics> users(@RequestParam(required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate dateFrom,
                                                        @RequestParam(required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate dateTo) {
        return ApiEnvelope.success("Lấy phân tích người dùng thành công.",service.users(dateFrom,dateTo));
    }
    @PreAuthorize("hasAuthority('analytics:read')")
    @GetMapping("/ai")
    ApiEnvelope<AdminAnalyticsDtos.AiAnalytics> ai(@RequestParam(required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate dateFrom,
                                                   @RequestParam(required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate dateTo,
                                                   @RequestParam(defaultValue="20") @Min(1) @Max(100) int topLimit) {
        return ApiEnvelope.success("Lấy phân tích AI thành công.",service.ai(dateFrom,dateTo,topLimit));
    }
    @PreAuthorize("hasAuthority('risk:read')")
    @GetMapping("/security")
    ApiEnvelope<AdminAnalyticsDtos.SecurityAnalytics> security(@RequestParam(required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate dateFrom,
                                                               @RequestParam(required=false) @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate dateTo) {
        return ApiEnvelope.success("Lấy phân tích bảo mật thành công.",service.security(dateFrom,dateTo));
    }
    @PreAuthorize("hasAuthority('system:config')")
    @PostMapping("/recompute")
    ApiEnvelope<Void> recompute(@RequestParam @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate dateFrom,
                                @RequestParam @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate dateTo) {
        service.recompute(dateFrom,dateTo);
        return ApiEnvelope.success("Đã tính lại số liệu phân tích.",null);
    }
}
