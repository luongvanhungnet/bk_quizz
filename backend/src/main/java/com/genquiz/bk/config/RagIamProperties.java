package com.genquiz.bk.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "bkquiz.rag.iam")
public record RagIamProperties(boolean enabled, String audience) {
    public RagIamProperties {
        audience = audience == null ? "" : audience.trim().replaceAll("/$", "");
    }
}
