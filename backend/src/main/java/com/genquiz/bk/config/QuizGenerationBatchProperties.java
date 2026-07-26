package com.genquiz.bk.config;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "bkquiz.quiz-generation")
public record QuizGenerationBatchProperties(
        @Min(1) @Max(4) int batchMaxQuestions,
        @Min(1) @Max(5) int batchMaxAttempts,
        @NotNull Duration batchRetryDelay,
        @NotNull Duration batchSuccessDelay) {
}
