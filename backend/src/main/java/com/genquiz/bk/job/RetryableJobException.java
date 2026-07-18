package com.genquiz.bk.job;

import java.time.Duration;

public class RetryableJobException extends RuntimeException {
    private final Duration retryAfter;
    public RetryableJobException(String message, Duration retryAfter, Throwable cause) {
        super(message, cause); this.retryAfter = retryAfter;
    }
    public RetryableJobException(String message, Duration retryAfter) { this(message, retryAfter, null); }
    public Duration retryAfter() { return retryAfter; }
}
