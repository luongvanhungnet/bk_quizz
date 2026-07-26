package com.genquiz.bk.config;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "bkquiz.rag")
public record RagProperties(
        boolean enabled,
        @NotBlank String baseUrl,
        String internalApiKey,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout) {}
