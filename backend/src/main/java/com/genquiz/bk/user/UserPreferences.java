package com.genquiz.bk.user;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.MapsId;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;

import java.util.UUID;

@Entity
@Table(name = "user_preferences")
public class UserPreferences {
    @Id
    @Column(name = "user_id")
    private UUID userId;

    @MapsId
    @OneToOne(optional = false)
    @jakarta.persistence.JoinColumn(name = "user_id")
    private User user;

    @Column(name = "email_study_reminders", nullable = false)
    private boolean emailStudyReminders = true;

    @Column(name = "public_profile", nullable = false)
    private boolean publicProfile;

    @Column(name = "attempt_autosave", nullable = false)
    private boolean attemptAutosave = true;

    protected UserPreferences() {}

    public UserPreferences(User user) { this.user = user; }

    public UUID getUserId() { return userId; }
    public boolean isEmailStudyReminders() { return emailStudyReminders; }
    public void setEmailStudyReminders(boolean value) { emailStudyReminders = value; }
    public boolean isPublicProfile() { return publicProfile; }
    public void setPublicProfile(boolean value) { publicProfile = value; }
    public boolean isAttemptAutosave() { return attemptAutosave; }
    public void setAttemptAutosave(boolean value) { attemptAutosave = value; }
}

