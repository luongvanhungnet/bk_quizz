package com.genquiz.bk.user;

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
@Table(name = "account_deletion_requests")
public class AccountDeletionRequest {
    @Id private UUID id;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;
    @Column(name = "cancel_token_hash", nullable = false, unique = true, length = 64)
    private String cancelTokenHash;
    @Column(nullable = false, length = 20) private String status = "PENDING";
    @Column(name = "requested_at", nullable = false) private Instant requestedAt;
    @Column(name = "execute_after", nullable = false) private Instant scheduledFor;
    @Column(name = "cancelled_at") private Instant cancelledAt;
    @Column(name = "completed_at") private Instant processedAt;
    @Column(name = "created_at", nullable = false) private Instant createdAt;
    @Column(name = "updated_at", nullable = false) private Instant updatedAt;
    @jakarta.persistence.Version private long version;
    protected AccountDeletionRequest() {}
    public AccountDeletionRequest(User user, String cancelTokenHash, Instant scheduledFor) {
        this.id = UUID.randomUUID(); this.user = user; this.cancelTokenHash = cancelTokenHash;
        this.scheduledFor = scheduledFor;
    }
    @PrePersist void init() {
        Instant now = Instant.now();
        if (requestedAt == null) requestedAt = now;
        if (createdAt == null) createdAt = now;
        updatedAt = now;
    }
    @jakarta.persistence.PreUpdate void touch() { updatedAt = Instant.now(); }
    public User getUser() { return user; }
    public UUID getId() { return id; }
    public boolean isPending() { return "PENDING".equals(status); }
    public void cancel() { cancelledAt = Instant.now(); status = "CANCELLED"; }
    public void processed() { processedAt = Instant.now(); status = "COMPLETED"; }
    public Instant getScheduledFor() { return scheduledFor; }
}
