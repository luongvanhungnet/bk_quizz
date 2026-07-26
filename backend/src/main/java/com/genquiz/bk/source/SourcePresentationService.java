package com.genquiz.bk.source;

import com.genquiz.bk.job.JobWorkerPresenceService;
import com.genquiz.bk.rag.RagProcessorHealthService;
import java.time.Clock;
import java.time.Instant;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class SourcePresentationService {
    private final JobWorkerPresenceService workers;
    private final RagProcessorHealthService ragHealth;
    private final Clock clock;

    @Autowired
    public SourcePresentationService(JobWorkerPresenceService workers, RagProcessorHealthService ragHealth) {
        this(workers, ragHealth, Clock.systemUTC());
    }

    SourcePresentationService(JobWorkerPresenceService workers, RagProcessorHealthService ragHealth, Clock clock) {
        this.workers = workers;
        this.ragHealth = ragHealth;
        this.clock = clock;
    }

    public SourceDtos.Response response(SourceDocument source) {
        boolean available = workers.isAvailable() && ragHealth.snapshot().workerAvailable();
        return SourceDtos.Response.from(source, available, Instant.now(clock));
    }
}
