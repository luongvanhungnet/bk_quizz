package com.genquiz.bk.job;

import com.genquiz.bk.config.AppProperties;
import com.genquiz.bk.config.RagProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class JobWorkerStartupReporter {
    private static final Logger log = LoggerFactory.getLogger(JobWorkerStartupReporter.class);
    private final AppProperties properties;
    private final RagProperties rag;
    private final JobService jobs;

    public JobWorkerStartupReporter(AppProperties properties, RagProperties rag, JobService jobs) {
        this.properties = properties;
        this.rag = rag;
        this.jobs = jobs;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void report() {
        var queue = jobs.documentQueueHealth();
        if (properties.jobs().workerEnabled()) {
            log.info("Document processor mode=ENABLED pollDelay={} ragEnabled={} ragUrl={} queuedJobs={}",
                    properties.jobs().pollDelay(), rag.enabled(), rag.baseUrl(), queue.queuedJobs());
        } else {
            log.warn("Document processor mode=DISABLED ragEnabled={} ragUrl={} queuedJobs={}. "
                            + "A separate BKQuiz worker process must be running.",
                    rag.enabled(), rag.baseUrl(), queue.queuedJobs());
        }
    }
}
