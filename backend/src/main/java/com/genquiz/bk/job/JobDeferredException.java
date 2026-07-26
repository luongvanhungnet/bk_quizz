package com.genquiz.bk.job;

import java.time.Duration;

public class JobDeferredException extends RuntimeException {
    private final Duration delay;

    public JobDeferredException(Duration delay) {
        super("Job is waiting for an upstream operation.");
        this.delay = delay;
    }

    public Duration delay() { return delay; }
}
