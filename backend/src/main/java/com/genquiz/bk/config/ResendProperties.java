package com.genquiz.bk.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "resend.api")
public record ResendProperties(String key, String url, Duration connectTimeout, Duration readTimeout) {}
