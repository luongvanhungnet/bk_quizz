package com.genquiz.bk.user.dto;

import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;

import java.util.UUID;

public record UserDto(
        UUID id,
        String username,
        String email,
        Role role,
        String avatarUrl,
        String bio,
        boolean emailVerified,
        boolean active
) {
    public static UserDto from(User user) {
        String avatar = user.getAvatarFileId() == null ? user.getAvatarUrl()
                : "/api/avatars/" + user.getId() + "?v=" + user.getAvatarFileId();
        return new UserDto(user.getId(), user.getUsername(), user.getEmail(), user.getRole(),
                avatar, user.getBio(), user.isEmailVerified(), user.isActive());
    }
}
