package com.genquiz.bk.config;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "bkquiz.realtime")
public record RealtimeProperties(
        @NotBlank String provider,
        String ablyApiKey,
        @NotBlank String channelPrefix,
        @Min(60) @Max(3600) long tokenTtlSeconds,
        boolean publishEnabled
) {
    public boolean usesAbly() {
        return "ably".equalsIgnoreCase(provider);
    }

    public Duration tokenTtl() {
        return Duration.ofSeconds(tokenTtlSeconds);
    }

    public String classroomChannel(java.util.UUID classroomId) {
        return channelPrefix + classroomId;
    }
}
