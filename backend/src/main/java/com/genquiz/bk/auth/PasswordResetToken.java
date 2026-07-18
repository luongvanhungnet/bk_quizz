package com.genquiz.bk.auth;

import com.genquiz.bk.user.User;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "password_reset_tokens")
public class PasswordResetToken {
    @Id private UUID id;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;
    @Column(name = "token_hash", nullable = false, unique = true, length = 64)
    private String tokenHash;
    @Column(name = "expires_at", nullable = false) private Instant expiresAt;
    @Column(name = "used_at") private Instant usedAt;
    @Column(name = "created_at", nullable = false) private Instant createdAt;
    protected PasswordResetToken() {}
    public PasswordResetToken(User user, String tokenHash, Instant expiresAt) {
        this.id = UUID.randomUUID(); this.user = user; this.tokenHash = tokenHash; this.expiresAt = expiresAt;
    }
    @PrePersist void init() { if (createdAt == null) createdAt = Instant.now(); }
    public User getUser() { return user; }
    public UUID getId() { return id; }
    public boolean isUsable() { return usedAt == null && expiresAt.isAfter(Instant.now()); }
    public void use() { usedAt = Instant.now(); }
}
