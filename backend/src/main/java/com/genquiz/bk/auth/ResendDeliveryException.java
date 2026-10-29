package com.genquiz.bk.auth;

import com.genquiz.bk.job.NonRetryableJobException;

public class ResendDeliveryException extends NonRetryableJobException {
    private final String code;

    public ResendDeliveryException(String code, String message) {
        super(message);
        this.code = code;
    }

    public ResendDeliveryException(String code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
