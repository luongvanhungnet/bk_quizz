package com.genquiz.bk.user;

import com.genquiz.bk.auth.dto.TokenRequest;
import com.genquiz.bk.common.api.ApiEnvelope;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AccountDeletionController {
    private final UserService users;
    public AccountDeletionController(UserService users) { this.users = users; }
    @PostMapping("/cancel-deletion") ApiEnvelope<Void> cancel(@Valid @RequestBody TokenRequest request) {
        users.cancelDeletion(request.token());
        return ApiEnvelope.success("Đã hủy yêu cầu xóa tài khoản.", null);
    }
}
