package com.genquiz.bk.auth.dto;

import com.genquiz.bk.user.dto.UserDto;

public record AuthPayload(String accessToken, long expiresIn, UserDto user) {}

