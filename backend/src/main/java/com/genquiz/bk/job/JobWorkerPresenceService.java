package com.genquiz.bk.job;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JobWorkerPresenceService {
    public static final Duration FRESHNESS = Duration.ofSeconds(30);
    private final JobWorkerHeartbeatRepository heartbeats;
    private final Clock clock;
    private volatile Instant cacheCheckedAt = Instant.EPOCH;
    private volatile boolean cachedAvailable;

    @Autowired
    public JobWorkerPresenceService(JobWorkerHeartbeatRepository heartbeats) {
        this(heartbeats, Clock.systemUTC());
    }

    JobWorkerPresenceService(JobWorkerHeartbeatRepository heartbeats, Clock clock) {
        this.heartbeats = heartbeats;
        this.clock = clock;
    }

    @Transactional
    public void heartbeat(String workerId) {
        Instant now = Instant.now(clock);
        JobWorkerHeartbeat heartbeat = heartbeats.findById(workerId)
                .orElseGet(() -> new JobWorkerHeartbeat(workerId, now));
        heartbeat.touch(now);
        heartbeats.save(heartbeat);
        cachedAvailable = true;
        cacheCheckedAt = now;
    }

    @Transactional(readOnly = true)
    public boolean isAvailable() {
        Instant now = Instant.now(clock);
        if (cacheCheckedAt.isAfter(now.minusSeconds(5))) {
            return cachedAvailable;
        }
        cachedAvailable = heartbeats.countByLastSeenAtGreaterThanEqual(now.minus(FRESHNESS)) > 0;
        cacheCheckedAt = now;
        return cachedAvailable;
    }
}
