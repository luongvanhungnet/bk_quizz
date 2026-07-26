package com.genquiz.bk.rag;

import java.time.Duration;

public class RagServiceException extends RuntimeException {
    private final String code;
    private final boolean retryable;
    private final Duration retryAfter;
    private final String upstreamRequestId;

    public RagServiceException(String code, String message, boolean retryable,
                               Duration retryAfter, String upstreamRequestId, Throwable cause) {
        super(message, cause);
        this.code = code; this.retryable = retryable; this.retryAfter = retryAfter;
        this.upstreamRequestId = upstreamRequestId;
    }
    public String code() { return code; }
    public boolean retryable() { return retryable; }
    public Duration retryAfter() { return retryAfter; }
    public String upstreamRequestId() { return upstreamRequestId; }
}
