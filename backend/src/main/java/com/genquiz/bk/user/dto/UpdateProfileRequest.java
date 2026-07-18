package com.genquiz.bk.user.dto;

import jakarta.validation.constraints.Size;

public record UpdateProfileRequest(
        @Size(min = 3, max = 50, message = "Tên hiển thị phải có từ 3 đến 50 ký tự.") String username,
        @Size(max = 2048, message = "Đường dẫn ảnh đại diện quá dài.") String avatarUrl,
        @Size(max = 500, message = "Tiểu sử không được vượt quá 500 ký tự.") String bio
) {}

