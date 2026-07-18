package com.genquiz.bk.common.api;

public record ApiFieldError(String code, String field, String message) {
    public ApiFieldError(String code, String message) {
        this(code, null, message);
    }
}

