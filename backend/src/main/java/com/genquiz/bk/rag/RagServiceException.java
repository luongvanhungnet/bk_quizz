package com.genquiz.bk.rag;

import java.time.Duration;
import tools.jackson.databind.JsonNode;

public class RagServiceException extends RuntimeException {
    private final String code;
    private final boolean retryable;
    private final Duration retryAfter;
    private final String upstreamRequestId;
    private final JsonNode details;

    public RagServiceException(String code, String message, boolean retryable,
                               Duration retryAfter, String upstreamRequestId, Throwable cause) {
        this(code, message, retryable, retryAfter, upstreamRequestId, null, cause);
    }

    public RagServiceException(String code, String message, boolean retryable,
                               Duration retryAfter, String upstreamRequestId,
                               JsonNode details, Throwable cause) {
        super(message, cause);
        this.code = code; this.retryable = retryable; this.retryAfter = retryAfter;
        this.upstreamRequestId = upstreamRequestId;
        this.details = details;
    }
    public String code() { return code; }
    public boolean retryable() { return retryable; }
    public Duration retryAfter() { return retryAfter; }
    public String upstreamRequestId() { return upstreamRequestId; }
    public JsonNode details() { return details; }
}
