package com.genquiz.bk.user;

import com.genquiz.bk.auth.dto.TokenRequest;
import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.security.CurrentUser;
import com.genquiz.bk.user.dto.DeleteAccountRequest;
import com.genquiz.bk.user.dto.PreferencesDto;
import com.genquiz.bk.user.dto.UpdatePreferencesRequest;
import com.genquiz.bk.user.dto.UpdateProfileRequest;
import com.genquiz.bk.user.dto.UserDto;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/users/me")
public class UserController {
    private final CurrentUser current;
    private final UserService service;
    private final DashboardService dashboard;
    public UserController(CurrentUser current, UserService service, DashboardService dashboard) {
        this.current = current; this.service = service; this.dashboard = dashboard;
    }

    @GetMapping("/profile") ApiEnvelope<UserDto> profile() {
        return ApiEnvelope.success("Lấy hồ sơ thành công.", UserDto.from(current.require()));
    }
    @PutMapping("/profile") ApiEnvelope<UserDto> update(@Valid @RequestBody UpdateProfileRequest request) {
        return ApiEnvelope.success("Cập nhật hồ sơ thành công.", service.updateProfile(request));
    }
    @GetMapping("/preferences") ApiEnvelope<PreferencesDto> preferences() {
        return ApiEnvelope.success("Lấy cài đặt thành công.", service.preferences());
    }
    @GetMapping("/dashboard") ApiEnvelope<DashboardDtos.Response> dashboard() {
        return ApiEnvelope.success("Lấy dữ liệu tổng quan thành công.", dashboard.get(current.require().getId()));
    }
    @PutMapping("/preferences") ApiEnvelope<PreferencesDto> updatePreferences(@RequestBody UpdatePreferencesRequest request) {
        return ApiEnvelope.success("Cập nhật cài đặt thành công.", service.updatePreferences(request));
    }
    @PostMapping("/deletion-request") ApiEnvelope<Void> delete(@Valid @RequestBody DeleteAccountRequest request) {
        service.requestDeletion(request.password());
        return ApiEnvelope.success("Yêu cầu xóa tài khoản đã được ghi nhận. Bạn có 30 ngày để hủy.", null);
    }
}
