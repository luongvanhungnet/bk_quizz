package com.genquiz.bk.config;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.util.Arrays;

@Component
public class StartupSecurityValidator implements ApplicationRunner {
    private final AppProperties properties;
    private final Environment environment;
    public StartupSecurityValidator(AppProperties properties, Environment environment) {
        this.properties = properties; this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        properties.frontendOrigins().forEach(this::validateOrigin);
        boolean production = Arrays.asList(environment.getActiveProfiles()).contains("prod");
        if (production) {
            if (properties.security().accessSecret().contains("change-me")
                    || properties.security().accessSecret().contains("development")) {
                throw new IllegalStateException("JWT_ACCESS_SECRET production phải là secret ngẫu nhiên, không dùng giá trị mẫu.");
            }
            if (!properties.security().cookieSecure()) {
                throw new IllegalStateException("COOKIE_SECURE phải được bật trong production.");
            }
            if (properties.frontendOrigins().stream().anyMatch(origin -> origin.contains("localhost"))) {
                throw new IllegalStateException("FRONTEND_ORIGINS production không được chứa localhost.");
            }
        }
        if (properties.ai().enabled() && environment.getProperty("spring.ai.google.genai.api-key", "").isBlank()) {
            throw new IllegalStateException("GEMINI_API_KEY là bắt buộc khi AI_ENABLED=true.");
        }
    }

    private void validateOrigin(String origin) {
        if (origin.contains("*")) {
            throw new IllegalStateException(
                    "FRONTEND_ORIGINS không được chứa wildcard khi CORS cho phép credentials.");
        }
        URI uri;
        try { uri = URI.create(origin); }
        catch (IllegalArgumentException exception) { throw new IllegalStateException("FRONTEND_ORIGINS chứa URL không hợp lệ."); }
        if (uri.getScheme() == null || uri.getHost() == null || uri.getPath() != null && !uri.getPath().isEmpty()) {
            throw new IllegalStateException("Mỗi FRONTEND_ORIGINS phải chỉ gồm scheme, host và port.");
        }
    }
}
