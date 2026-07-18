package com.genquiz.bk.notification;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

public interface NotificationRepository extends JpaRepository<Notification, UUID> {
    @Query("select n from Notification n where n.userId = :userId " +
            "and (:unreadOnly = false or n.readAt is null) and (n.expiresAt is null or n.expiresAt > :now) " +
            "order by n.createdAt desc")
    Page<Notification> list(UUID userId, boolean unreadOnly, Instant now, Pageable pageable);

    Optional<Notification> findByIdAndUserId(UUID id, UUID userId);
    @Query("select count(n) from Notification n where n.userId = :userId and n.readAt is null " +
            "and (n.expiresAt is null or n.expiresAt > :now)")
    long countUnread(UUID userId, Instant now);
    boolean existsByUserIdAndDeduplicationKey(UUID userId, String deduplicationKey);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update Notification n set n.readAt = :now, n.updatedAt = :now, n.version = n.version + 1 " +
            "where n.userId = :userId and n.readAt is null")
    int markAllRead(UUID userId, Instant now);
}
