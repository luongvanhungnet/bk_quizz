package com.genquiz.bk.classroom;

import com.genquiz.bk.config.RealtimeProperties;
import io.ably.lib.rest.AblyRest;
import io.ably.lib.types.AblyException;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConditionalOnProperty(name = "bkquiz.realtime.provider", havingValue = "ably")
class AblyConfiguration {
    @Bean(destroyMethod = "close")
    AblyRest ablyRest(RealtimeProperties properties) throws AblyException {
        String apiKey = properties.ablyApiKey() == null ? "" : properties.ablyApiKey().trim();
        if (apiKey.isEmpty()) {
            throw new IllegalStateException("ABLY_API_KEY is required when REALTIME_PROVIDER=ably.");
        }
        return new AblyRest(apiKey);
    }
}
