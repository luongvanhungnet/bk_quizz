package com.genquiz.bk.security;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
public class CurrentUser {
    private final UserRepository users;

    public CurrentUser(UserRepository users) { this.users = users; }

    public UUID id() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || !authentication.isAuthenticated() || "anonymousUser".equals(authentication.getPrincipal())) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "AUTH_REQUIRED", "Bạn cần đăng nhập để tiếp tục.");
        }
        try { return UUID.fromString(authentication.getName()); }
        catch (IllegalArgumentException exception) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_ACCESS_TOKEN", "Phiên đăng nhập không hợp lệ.");
        }
    }

    public User require() {
        User user = users.findById(id()).orElseThrow(() ->
                new ApiException(HttpStatus.UNAUTHORIZED, "USER_NOT_FOUND", "Tài khoản không còn tồn tại."));
        if (!user.isActive() || user.getDeletedAt() != null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "ACCOUNT_INACTIVE", "Tài khoản đã bị khóa hoặc xóa.");
        }
        return user;
    }

    public void requireVerified() {
        if (!require().isEmailVerified()) {
            throw new ApiException(HttpStatus.FORBIDDEN, "EMAIL_NOT_VERIFIED",
                    "Bạn cần xác minh email trước khi thực hiện thao tác này.");
        }
    }
}

