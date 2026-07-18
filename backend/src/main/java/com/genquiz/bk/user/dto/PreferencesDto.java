package com.genquiz.bk.user.dto;

import com.genquiz.bk.user.UserPreferences;

public record PreferencesDto(boolean emailStudyReminders, boolean publicProfile, boolean attemptAutosave) {
    public static PreferencesDto from(UserPreferences value) {
        return new PreferencesDto(value.isEmailStudyReminders(), value.isPublicProfile(), value.isAttemptAutosave());
    }
}

