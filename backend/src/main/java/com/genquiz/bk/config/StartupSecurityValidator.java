package com.genquiz.bk.config;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.util.Arrays;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Component
public class StartupSecurityValidator implements ApplicationRunner {
    private static final Logger log = LoggerFactory.getLogger(StartupSecurityValidator.class);
    private final AppProperties properties;
    private final Environment environment;
    public StartupSecurityValidator(AppProperties properties, Environment environment) {
        this.properties = properties; this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        properties.frontendOrigins().forEach(this::validateOrigin);
        boolean cloudRun = !environment.getProperty("K_SERVICE", "").isBlank();
        boolean production = cloudRun || Arrays.asList(environment.getActiveProfiles()).contains("prod");
        if (production) {
            if (properties.security().accessSecret().contains("change-me")
                    || properties.security().accessSecret().contains("development")) {
                throw new IllegalStateException("JWT_ACCESS_SECRET production phải là secret ngẫu nhiên, không dùng giá trị mẫu.");
            }
            if (!properties.security().cookieSecure()) {
                throw new IllegalStateException("COOKIE_SECURE phải được bật trong production.");
            }
            if (properties.frontendOrigins().stream().anyMatch(origin -> origin.contains("localhost"))) {
                throw new IllegalStateException(
                        "FRONTEND_ORIGINS production không được chứa localhost. "
                                + "Hãy đặt origin HTTPS thật của Cloudflare Pages hoặc custom domain, "
                                + "ví dụ https://bkquiz.pages.dev.");
            }
            validateProductionStorage();
            URI storageEndpoint = URI.create(properties.storage().endpoint());
            log.info("Object storage configured provider=s3 endpointHost={} region={} bucket={} cloudRun={}",
                    storageEndpoint.getHost(), properties.storage().region(), properties.storage().bucket(), cloudRun);
        }
        if (properties.ai().enabled() && environment.getProperty("spring.ai.google.genai.api-key", "").isBlank()) {
            throw new IllegalStateException("GEMINI_API_KEY là bắt buộc khi AI_ENABLED=true.");
        }
    }

    private void validateProductionStorage() {
        String provider = environment.getProperty("bkquiz.storage.provider", "local");
        if (!"s3".equalsIgnoreCase(provider)) {
            throw new IllegalStateException(
                    "STORAGE_PROVIDER production phải là s3 vì filesystem Cloud Run không lưu trữ bền vững.");
        }
        URI endpoint;
        try { endpoint = URI.create(properties.storage().endpoint()); }
        catch (IllegalArgumentException exception) {
            throw new IllegalStateException("S3_ENDPOINT production không hợp lệ.", exception);
        }
        if (!"https".equalsIgnoreCase(endpoint.getScheme()) || endpoint.getHost() == null
                || !endpoint.getHost().endsWith(".r2.cloudflarestorage.com")) {
            throw new IllegalStateException(
                    "S3_ENDPOINT production phải là endpoint HTTPS S3 API của Cloudflare R2.");
        }
        if (!"auto".equalsIgnoreCase(properties.storage().region())) {
            throw new IllegalStateException("S3_REGION cho Cloudflare R2 phải là auto.");
        }
        if (properties.storage().accessKey().equalsIgnoreCase("minioadmin")
                || properties.storage().secretKey().equalsIgnoreCase("minioadmin")
                || properties.storage().secretKey().contains("replace_me")) {
            throw new IllegalStateException("Thông tin xác thực Cloudflare R2 production vẫn dùng giá trị mẫu.");
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
