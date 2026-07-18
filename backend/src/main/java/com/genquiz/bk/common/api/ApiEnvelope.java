package com.genquiz.bk.common.api;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ApiEnvelope<T>(
        boolean success,
        String message,
        T data,
        PageMetadata pagination,
        List<ApiFieldError> errors,
        String traceId
) {
    public static <T> ApiEnvelope<T> success(String message, T data) {
        return new ApiEnvelope<>(true, message, data, null, null, null);
    }

    public static <T> ApiEnvelope<T> page(String message, T data, PageMetadata pagination) {
        return new ApiEnvelope<>(true, message, data, pagination, null, null);
    }

    public static ApiEnvelope<Void> failure(String message, List<ApiFieldError> errors, String traceId) {
        return new ApiEnvelope<>(false, message, null, null, List.copyOf(errors), traceId);
    }
}

