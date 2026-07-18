package com.genquiz.bk.user;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "users")
public class User {
    @Id
    private UUID id;

    @Column(nullable = false, length = 50)
    private String username;

    @Column(nullable = false, unique = true, columnDefinition = "citext")
    private String email;

    @Column(name = "password_hash", nullable = false, length = 100)
    private String passwordHash;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Role role = Role.STUDENT;

    @Column(name = "avatar_url", length = 2048)
    private String avatarUrl;

    @Column(name = "avatar_file_id")
    private UUID avatarFileId;

    @Column(length = 500)
    private String bio;

    @Column(nullable = false)
    private boolean active = true;

    @Column(name = "email_verified_at")
    private Instant emailVerifiedAt;

    @Column(name = "deletion_requested_at")
    private Instant deletionRequestedAt;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    private long version;

    protected User() {}

    public User(String username, String email, String passwordHash) {
        this.id = UUID.randomUUID();
        this.username = username;
        this.email = email;
        this.passwordHash = passwordHash;
    }

    @PrePersist
    void initializeTimestamps() {
        Instant now = Instant.now();
        if (id == null) id = UUID.randomUUID();
        if (createdAt == null) createdAt = now;
        updatedAt = now;
    }

    @jakarta.persistence.PreUpdate
    void updateTimestamp() { updatedAt = Instant.now(); }

    public UUID getId() { return id; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getPasswordHash() { return passwordHash; }
    public void setPasswordHash(String passwordHash) { this.passwordHash = passwordHash; }
    public Role getRole() { return role; }
    public void setRole(Role role) { this.role = role; }
    public String getAvatarUrl() { return avatarUrl; }
    public void setAvatarUrl(String avatarUrl) { this.avatarUrl = avatarUrl; }
    public UUID getAvatarFileId() { return avatarFileId; }
    public void setAvatarFileId(UUID avatarFileId) { this.avatarFileId = avatarFileId; this.avatarUrl = null; }
    public String getBio() { return bio; }
    public void setBio(String bio) { this.bio = bio; }
    public boolean isActive() { return active; }
    public void setActive(boolean active) { this.active = active; }
    public Instant getEmailVerifiedAt() { return emailVerifiedAt; }
    public void verifyEmail() { this.emailVerifiedAt = Instant.now(); }
    public boolean isEmailVerified() { return emailVerifiedAt != null; }
    public Instant getDeletionRequestedAt() { return deletionRequestedAt; }
    public void requestDeletion() { this.deletionRequestedAt = Instant.now(); this.active = false; }
    public void cancelDeletion() { this.deletionRequestedAt = null; this.active = true; }
    public Instant getDeletedAt() { return deletedAt; }
    public void anonymize() {
        this.deletedAt = Instant.now();
        this.active = false;
        this.username = "Người dùng đã xóa";
        this.email = "deleted-" + id + "@anonymized.invalid";
        this.avatarUrl = null;
        this.avatarFileId = null;
        this.bio = null;
        this.passwordHash = "!deleted-account-password-hash-disabled-000000000000000000000000!";
    }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public long getVersion() { return version; }
}
