package com.genquiz.bk.common.error;

import com.genquiz.bk.common.api.ApiFieldError;
import org.springframework.http.HttpStatus;

import java.util.List;

public class ApiException extends RuntimeException {
    private final HttpStatus status;
    private final String code;
    private final List<ApiFieldError> errors;

    public ApiException(HttpStatus status, String code, String message) {
        this(status, code, message, List.of(new ApiFieldError(code, message)));
    }

    public ApiException(HttpStatus status, String code, String message, List<ApiFieldError> errors) {
        super(message);
        this.status = status;
        this.code = code;
        this.errors = List.copyOf(errors);
    }

    public HttpStatus status() { return status; }
    public String code() { return code; }
    public List<ApiFieldError> errors() { return errors; }
}

