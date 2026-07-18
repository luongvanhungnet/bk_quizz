package com.genquiz.bk.common.api;

public record PageMetadata(
        int page,
        int limit,
        long totalItems,
        int totalPages,
        boolean hasNextPage,
        boolean hasPreviousPage
) {}

