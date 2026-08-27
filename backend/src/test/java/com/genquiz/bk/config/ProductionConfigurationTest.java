package com.genquiz.bk.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import org.junit.jupiter.api.Test;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mock.env.MockEnvironment;

class ProductionConfigurationTest {

    @Test
    void productionUsesSafeCloudRunDefaults() {
        var environment = productionEnvironment()
                .withProperty("DATABASE_URL", "jdbc:postgresql://pooler.example.neon.tech/bkquiz?sslmode=require")
                .withProperty("DATABASE_USERNAME", "runtime_user")
                .withProperty("DATABASE_PASSWORD", "test-only-password")
                .withProperty("FRONTEND_ORIGINS", "https://quiz.example.com")
                .withProperty("JWT_ACCESS_SECRET", "test-only-production-access-secret-32-characters");

        assertThat(environment.getProperty("server.port")).isEqualTo("8080");
        assertThat(environment.getProperty("spring.datasource.url"))
                .isEqualTo("jdbc:postgresql://pooler.example.neon.tech/bkquiz?sslmode=require");
        assertThat(environment.getProperty("spring.datasource.hikari.maximum-pool-size"))
                .isEqualTo("4");
        assertThat(environment.getProperty("spring.flyway.enabled")).isEqualTo("false");
        assertThat(environment.getProperty("bkquiz.jobs.worker-enabled")).isEqualTo("false");
        assertThat(environment.getProperty("bkquiz.security.cookie-secure")).isEqualTo("true");
        assertThat(environment.getProperty("bkquiz.storage.local-root"))
                .isEqualTo("/tmp/bkquiz/uploads");
    }

    @Test
    void productionEnvironmentOverridesAreLoaded() {
        var environment = productionEnvironment()
                .withProperty("PORT", "9090")
                .withProperty("DATABASE_URL", "jdbc:postgresql://pooler.example.neon.tech/bkquiz?sslmode=verify-full")
                .withProperty("DATABASE_USERNAME", "runtime_user")
                .withProperty("DATABASE_PASSWORD", "test-only-password")
                .withProperty("DATABASE_POOL_SIZE", "7")
                .withProperty("FRONTEND_ORIGINS", "https://quiz.example.com")
                .withProperty("COOKIE_SECURE", "false")
                .withProperty("WORKER_ENABLED", "true")
                .withProperty("FLYWAY_ENABLED", "true");

        assertThat(environment.getProperty("server.port")).isEqualTo("9090");
        assertThat(environment.getProperty("spring.datasource.hikari.maximum-pool-size"))
                .isEqualTo("7");
        assertThat(environment.getProperty("spring.flyway.enabled")).isEqualTo("true");
        assertThat(environment.getProperty("bkquiz.jobs.worker-enabled")).isEqualTo("true");
        assertThat(environment.getProperty("bkquiz.security.cookie-secure")).isEqualTo("false");
        assertThat(environment.getProperty("bkquiz.frontend-origins"))
                .isEqualTo("https://quiz.example.com");
        assertThat(environment.getProperty("spring.datasource.url"))
                .endsWith("sslmode=verify-full");
    }

    private MockEnvironment productionEnvironment() {
        try {
            var environment = new MockEnvironment();
            var loader = new YamlPropertySourceLoader();
            var common = loader.load("application", new ClassPathResource("application.yml"));
            var production = loader.load("application-prod", new ClassPathResource("application-prod.yml"));
            for (PropertySource<?> source : common) {
                environment.getPropertySources().addLast(source);
            }
            for (int index = production.size() - 1; index >= 0; index--) {
                environment.getPropertySources().addAfter("mockProperties", production.get(index));
            }
            return environment;
        } catch (IOException exception) {
            throw new IllegalStateException("Không thể tải cấu hình production để kiểm thử.", exception);
        }
    }
}
