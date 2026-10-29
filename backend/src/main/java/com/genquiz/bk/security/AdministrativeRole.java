package com.genquiz.bk.security;

import java.util.Locale;

public enum AdministrativeRole {
    USER,
    SUPPORT,
    ANALYST,
    MODERATOR,
    ADMIN,
    OWNER;

    public static AdministrativeRole parse(String value) {
        if (value == null) throw new IllegalArgumentException("Role is required");
        return valueOf(value.trim().toUpperCase(Locale.ROOT));
    }

    public boolean privileged() {
        return this != USER;
    }
}
