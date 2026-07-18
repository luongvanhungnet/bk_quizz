package com.genquiz.bk.auth.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record ResetPasswordRequest(
        @NotBlank(message = "Token là bắt buộc.") String token,
        @NotBlank(message = "Mật khẩu là bắt buộc.")
        @Size(min = 8, max = 128, message = "Mật khẩu phải có từ 8 đến 128 ký tự.")
        @Pattern(regexp = "^(?=.*[a-z])(?=.*[A-Z])(?=.*\\d).+$",
                message = "Mật khẩu phải có chữ thường, chữ hoa và chữ số.")
        String password
) {}

