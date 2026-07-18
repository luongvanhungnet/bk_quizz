package com.genquiz.bk.auth.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record LoginRequest(
        @NotBlank(message = "Email là bắt buộc.") @Email(message = "Email không đúng định dạng.") String email,
        @NotBlank(message = "Mật khẩu là bắt buộc.") String password
) {}

