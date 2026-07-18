package com.genquiz.bk.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;
import java.util.List;

@Validated
@ConfigurationProperties(prefix = "bkquiz")
public record AppProperties(
        @NotEmpty List<@NotBlank String> frontendOrigins,
        @Valid Security security,
        @Valid Storage storage,
        @Valid Ai ai,
        @Valid Jobs jobs
) {
    public record Security(
            @Size(min = 32) String accessSecret,
            @NotNull Duration accessTtl,
            @NotNull Duration refreshTtl,
            @NotBlank String refreshCookieName,
            @NotBlank String xsrfCookieName,
            boolean cookieSecure,
            @Min(10) @Max(16) int bcryptStrength
    ) {}

    public record Storage(
            @NotBlank String endpoint,
            @NotBlank String region,
            @NotBlank String accessKey,
            @NotBlank String secretKey,
            @NotBlank String bucket,
            boolean pathStyle
    ) {}

    public record Ai(
            boolean enabled,
            @NotBlank String generationModel,
            @NotBlank String embeddingModel,
            @Min(128) @Max(3072) int embeddingDimensions,
            @NotNull Duration timeout,
            @Min(1) @Max(5) int maxAttempts,
            @Min(1) @Max(50) int maxQuestions,
            @Min(1) @Max(10) int maxSources,
            @Min(1) int minSourceCharacters
    ) {}

    public record Jobs(
            boolean workerEnabled,
            @NotNull Duration pollDelay,
            @NotNull Duration leaseDuration,
            @Min(1) @Max(20) int maxAttempts
    ) {}
}
