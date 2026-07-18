package com.genquiz.bk.user;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface AccountDeletionRequestRepository extends JpaRepository<AccountDeletionRequest, UUID> {
    Optional<AccountDeletionRequest> findFirstByUserIdAndStatus(UUID userId, String status);
    Optional<AccountDeletionRequest> findByCancelTokenHashAndStatus(String hash, String status);
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select r from AccountDeletionRequest r where r.status = 'PENDING' and r.scheduledFor <= :now")
    List<AccountDeletionRequest> findDue(Instant now);
}
