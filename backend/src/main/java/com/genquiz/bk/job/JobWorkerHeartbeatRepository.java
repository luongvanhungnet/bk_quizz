package com.genquiz.bk.job;

import java.time.Instant;
import org.springframework.data.jpa.repository.JpaRepository;

public interface JobWorkerHeartbeatRepository extends JpaRepository<JobWorkerHeartbeat, String> {
    long countByLastSeenAtGreaterThanEqual(Instant cutoff);
}
