package com.genquiz.bk.config;

import java.net.URI;
import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RagIamStartupValidator implements ApplicationRunner {
    private final RagProperties rag;
    private final RagIamProperties iam;
    private final Environment environment;

    public RagIamStartupValidator(
            RagProperties rag,
            RagIamProperties iam,
            Environment environment) {
        this.rag = rag;
        this.iam = iam;
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        boolean cloudRun = !environment.getProperty("K_SERVICE", "").isBlank();
        boolean production = cloudRun
                || Arrays.asList(environment.getActiveProfiles()).contains("prod");
        if (!production || !rag.enabled()) {
            return;
        }
        if (!iam.enabled()) {
            throw new IllegalStateException(
                    "RAG_IAM_ENABLED phải được bật khi RAG chạy trong production.");
        }
        URI audience;
        try {
            audience = URI.create(iam.audience());
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException("RAG_IAM_AUDIENCE không hợp lệ.", exception);
        }
        if (!"https".equalsIgnoreCase(audience.getScheme())
                || audience.getHost() == null
                || (audience.getPath() != null && !audience.getPath().isBlank())
                || audience.getQuery() != null
                || audience.getFragment() != null) {
            throw new IllegalStateException(
                    "RAG_IAM_AUDIENCE phải là origin HTTPS của Cloud Run RAG.");
        }
    }
}
