package com.genquiz.bk.auth;

import com.genquiz.bk.job.RetryableJobException;
import java.time.Duration;

public class ResendConnectivityException extends RetryableJobException {
    private final String code;

    public ResendConnectivityException(String code, String message, Duration retryAfter, Throwable cause) {
        super(message, retryAfter, cause);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
