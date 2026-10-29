package com.genquiz.bk.abuse;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.LocalDate;
import java.util.UUID;

public interface AtomicAbuseStore {
    AiAdmissionDecision admit(UUID userId, String leaseId, AbuseRequestIdentity identity, String endpoint,
                              ServiceLevel level, AntiAbuseProperties.LevelPolicy policy,
                              BigDecimal estimatedCost, LocalDate date);
    void release(UUID userId, String leaseId, String ipHash, String deviceHash);
    void adjustActualCost(UUID userId, LocalDate date, BigDecimal estimated, BigDecimal actual,
                          Duration ttl);
}
