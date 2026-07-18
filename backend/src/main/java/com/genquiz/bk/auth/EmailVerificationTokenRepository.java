package com.genquiz.bk.auth;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;
import java.util.UUID;
import java.time.Instant;

public interface EmailVerificationTokenRepository extends JpaRepository<EmailVerificationToken, UUID> {
    Optional<EmailVerificationToken> findByTokenHash(String tokenHash);
    boolean existsByIdAndUsedAtIsNullAndExpiresAtAfter(UUID id, Instant now);
    void deleteByUserId(UUID userId);
}
