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
                throw new IllegalStateException("Production JWT_ACCESS_SECRET must be a random secret, not a sample value.");
            }
            if (!properties.security().cookieSecure()) {
                throw new IllegalStateException("COOKIE_SECURE must be enabled in production.");
            }
            if (properties.frontendOrigins().stream().anyMatch(origin -> origin.contains("localhost"))) {
                throw new IllegalStateException(
                        "Production FRONTEND_ORIGINS must not contain localhost. "
                                + "Set the actual HTTPS Cloudflare Pages or custom-domain origin, "
                                + "for example https://bkquiz.pages.dev.");
            }
            validateProductionStorage();
            URI storageEndpoint = URI.create(properties.storage().endpoint());
            log.info("Object storage configured provider=s3 endpointHost={} region={} bucket={} cloudRun={}",
                    storageEndpoint.getHost(), properties.storage().region(), properties.storage().bucket(), cloudRun);
        }
        if (properties.ai().enabled() && environment.getProperty("spring.ai.google.genai.api-key", "").isBlank()) {
            throw new IllegalStateException("GEMINI_API_KEY is required when AI_ENABLED=true.");
        }
    }

    private void validateProductionStorage() {
        String provider = environment.getProperty("bkquiz.storage.provider", "local");
        if (!"s3".equalsIgnoreCase(provider)) {
            throw new IllegalStateException(
                    "Production STORAGE_PROVIDER must be s3 because the Cloud Run filesystem is not durable.");
        }
        URI endpoint;
        try { endpoint = URI.create(properties.storage().endpoint()); }
        catch (IllegalArgumentException exception) {
            throw new IllegalStateException("Production S3_ENDPOINT is invalid.", exception);
        }
        if (!"https".equalsIgnoreCase(endpoint.getScheme()) || endpoint.getHost() == null
                || !endpoint.getHost().endsWith(".r2.cloudflarestorage.com")) {
            throw new IllegalStateException(
                    "Production S3_ENDPOINT must be the HTTPS S3 API endpoint for Cloudflare R2.");
        }
        if (!"auto".equalsIgnoreCase(properties.storage().region())) {
            throw new IllegalStateException("S3_REGION must be auto for Cloudflare R2.");
        }
        if (properties.storage().accessKey().equalsIgnoreCase("minioadmin")
                || properties.storage().secretKey().equalsIgnoreCase("minioadmin")
                || properties.storage().secretKey().contains("replace_me")) {
            throw new IllegalStateException("Production Cloudflare R2 credentials still use sample values.");
        }
    }

    private void validateOrigin(String origin) {
        if (origin.contains("*")) {
            throw new IllegalStateException(
                    "FRONTEND_ORIGINS must not contain a wildcard when CORS credentials are enabled.");
        }
        URI uri;
        try { uri = URI.create(origin); }
        catch (IllegalArgumentException exception) { throw new IllegalStateException("FRONTEND_ORIGINS contains an invalid URL."); }
        if (uri.getScheme() == null || uri.getHost() == null || uri.getPath() != null && !uri.getPath().isEmpty()) {
            throw new IllegalStateException("Each FRONTEND_ORIGINS entry may contain only a scheme, host, and port.");
        }
    }
}
