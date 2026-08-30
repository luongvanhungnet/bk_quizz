package com.genquiz.bk.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;
import org.springframework.mock.env.MockEnvironment;

import java.time.Duration;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class StartupSecurityValidatorTest {
    @Test
    void cloudRunRejectsLocalStorageEvenWithoutProdProfile() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty("K_SERVICE", "bkquiz-api")
                .withProperty("bkquiz.storage.provider", "local");
        StartupSecurityValidator validator = new StartupSecurityValidator(properties(
                new AppProperties.Storage("http://localhost:9000", "us-east-1", "key", "secret", "bucket", true)),
                environment);

        assertThatThrownBy(() -> validator.run(new DefaultApplicationArguments()))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("STORAGE_PROVIDER");
    }

    private AppProperties properties(AppProperties.Storage storage) {
        return new AppProperties(
                List.of("https://quiz.example.com"),
                new AppProperties.Security("test-secret-at-least-32-characters-long", Duration.ofMinutes(15),
                        Duration.ofDays(7), "refresh", "XSRF-TOKEN", true, 12),
                storage,
                new AppProperties.Ai(false, "model", "embedding", 768, Duration.ofSeconds(60), 3, 100, 10, 100),
                new AppProperties.Jobs(false, Duration.ofSeconds(2), Duration.ofMinutes(2), 5));
    }
}
