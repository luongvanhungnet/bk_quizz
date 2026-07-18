package com.genquiz.bk.auth.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record RegisterRequest(
        @NotBlank(message = "Tên hiển thị là bắt buộc.")
        @Size(min = 3, max = 50, message = "Tên hiển thị phải có từ 3 đến 50 ký tự.")
        String username,
        @NotBlank(message = "Email là bắt buộc.")
        @Email(message = "Email không đúng định dạng.")
        String email,
        @NotBlank(message = "Mật khẩu là bắt buộc.")
        @Size(min = 8, max = 128, message = "Mật khẩu phải có từ 8 đến 128 ký tự.")
        @Pattern(regexp = "^(?=.*[a-z])(?=.*[A-Z])(?=.*\\d).+$",
                message = "Mật khẩu phải có chữ thường, chữ hoa và chữ số.")
        String password,
        AccountType accountType
) {
    public enum AccountType { STUDENT, TEACHER }
}
