package com.genquiz.bk.storage;

import com.genquiz.bk.config.AppProperties;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class StorageConfigTest {
    @Test
    void s3ClientDisablesChunkedEncodingForCloudflareR2() {
        var configuration = new StorageConfig().r2CompatibleConfiguration(properties().storage());
        assertThat(configuration.pathStyleAccessEnabled()).isTrue();
        assertThat(configuration.chunkedEncodingEnabled()).isFalse();
    }

    private AppProperties properties() {
        return new AppProperties(
                List.of("https://quiz.example.com"),
                new AppProperties.Security("test-secret-at-least-32-characters-long", Duration.ofMinutes(15),
                        Duration.ofDays(7), "refresh", "XSRF-TOKEN", true, 12),
                new AppProperties.Storage("https://account.r2.cloudflarestorage.com", "auto",
                        "access", "secret", "bkquiz-test", true),
                new AppProperties.Ai(false, "model", "embedding", 768, Duration.ofSeconds(60), 3, 100, 10, 100),
                new AppProperties.Jobs(false, Duration.ofSeconds(2), Duration.ofMinutes(2), 5));
    }
}
