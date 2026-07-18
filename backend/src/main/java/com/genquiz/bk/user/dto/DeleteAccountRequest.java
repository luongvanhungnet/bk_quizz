package com.genquiz.bk.user.dto;

import jakarta.validation.constraints.NotBlank;

public record DeleteAccountRequest(@NotBlank(message = "Mật khẩu là bắt buộc.") String password) {}

