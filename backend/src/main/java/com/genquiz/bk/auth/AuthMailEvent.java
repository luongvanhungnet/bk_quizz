package com.genquiz.bk.auth;

public record AuthMailEvent(Type type, String recipient, String username, String token) {
    public enum Type { VERIFY_EMAIL, RESET_PASSWORD, CANCEL_DELETION }
}

