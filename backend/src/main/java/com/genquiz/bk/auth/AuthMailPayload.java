package com.genquiz.bk.auth;

public record AuthMailPayload(
        AuthMailEvent.Type type,
        String recipient,
        String username,
        String encryptedToken
) {}
