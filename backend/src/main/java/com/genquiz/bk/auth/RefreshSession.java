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
@Table(name = "refresh_sessions")
public class RefreshSession {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "family_id", nullable = false)
    private UUID familyId;

    @Column(name = "token_hash", nullable = false, length = 64)
    private String tokenHash;

    @Column(name = "expires_at", nullable = false)
    private Instant expiresAt;

    @Column(name = "revoked_at")
    private Instant revokedAt;

    @Column(name = "replaced_by_id")
    private UUID replacedById;

    @Column(name = "user_agent", length = 500)
    private String userAgent;

    @Column(name = "ip_hash", length = 64)
    private String ipHash;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "last_used_at")
    private Instant lastUsedAt;

    protected RefreshSession() {}

    public RefreshSession(User user, UUID familyId, String tokenHash, Instant expiresAt,
                          String userAgent, String ipHash) {
        this.id = UUID.randomUUID();
        this.user = user;
        this.familyId = familyId;
        this.tokenHash = tokenHash;
        this.expiresAt = expiresAt;
        this.userAgent = userAgent;
        this.ipHash = ipHash;
    }

    @PrePersist
    void initialize() { if (id == null) id = UUID.randomUUID(); if (createdAt == null) createdAt = Instant.now(); }
    public UUID getId() { return id; }
    public User getUser() { return user; }
    public UUID getFamilyId() { return familyId; }
    public String getTokenHash() { return tokenHash; }
    public Instant getExpiresAt() { return expiresAt; }
    public Instant getRevokedAt() { return revokedAt; }
    public UUID getReplacedById() { return replacedById; }
    public boolean isUsable(Instant now) { return revokedAt == null && expiresAt.isAfter(now); }
    public void rotateTo(UUID replacement) { revokedAt = Instant.now(); replacedById = replacement; lastUsedAt = Instant.now(); }
    public void revoke() { if (revokedAt == null) revokedAt = Instant.now(); }
}

