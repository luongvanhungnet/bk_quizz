package com.genquiz.bk.security;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

@Component
public class VerifiedAccountGuard {
    private final UserRepository users;
    public VerifiedAccountGuard(UserRepository users) { this.users = users; }

    public User require(UUID userId) {
        User user = users.findByIdAndDeletedAtIsNull(userId).orElseThrow(() ->
                new ApiException(HttpStatus.UNAUTHORIZED, "USER_NOT_FOUND", "Tài khoản không còn tồn tại."));
        if (!user.isActive()) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "ACCOUNT_INACTIVE", "Tài khoản đã bị khóa hoặc xóa.");
        }
        if (!user.isEmailVerified()) {
            throw new ApiException(HttpStatus.FORBIDDEN, "EMAIL_NOT_VERIFIED",
                    "Bạn cần xác minh email trước khi thực hiện thao tác này.");
        }
        return user;
    }
}
