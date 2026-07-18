package com.genquiz.bk.auth.dto;

import jakarta.validation.constraints.NotBlank;

public record TokenRequest(@NotBlank(message = "Token là bắt buộc.") String token) {}

