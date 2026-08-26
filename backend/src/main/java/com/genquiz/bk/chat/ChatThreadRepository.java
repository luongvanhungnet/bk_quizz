package com.genquiz.bk.chat;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

public interface ChatThreadRepository extends JpaRepository<ChatThread, UUID> {
    Optional<ChatThread> findByIdAndUserIdAndDeletedAtIsNull(UUID id, UUID userId);
    Optional<ChatThread> findByAttemptIdAndUserIdAndDeletedAtIsNull(UUID attemptId, UUID userId);
    Page<ChatThread> findByUserIdAndDeletedAtIsNullOrderByUpdatedAtDesc(UUID userId, Pageable pageable);
    @Modifying @Query("update ChatThread t set t.status = com.genquiz.bk.chat.ChatThreadStatus.DELETED, " +
            "t.deletedAt = :now, t.updatedAt = :now where t.deletedAt is null and t.expiresAt <= :now")
    int softDeleteExpired(@Param("now") Instant now);
}
