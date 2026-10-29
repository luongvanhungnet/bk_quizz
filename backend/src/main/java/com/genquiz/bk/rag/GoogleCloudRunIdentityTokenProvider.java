package com.genquiz.bk.rag;

import com.google.auth.oauth2.AccessToken;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.IdTokenCredentials;
import com.google.auth.oauth2.IdTokenProvider;
import java.io.IOException;
import java.time.Instant;
import org.springframework.stereotype.Component;

@Component
public class GoogleCloudRunIdentityTokenProvider implements RagIdentityTokenProvider {
    private static final long REFRESH_SKEW_SECONDS = 60;
    private final Object lock = new Object();
    private volatile CachedToken cached;

    @Override
    public String token(String audience) {
        CachedToken current = cached;
        if (current != null && current.audience().equals(audience) && current.valid()) {
            return current.value();
        }
        synchronized (lock) {
            current = cached;
            if (current != null && current.audience().equals(audience) && current.valid()) {
                return current.value();
            }
            cached = obtain(audience);
            return cached.value();
        }
    }

    private CachedToken obtain(String audience) {
        if (audience == null || audience.isBlank()) {
            throw new IllegalStateException("RAG_IAM_AUDIENCE chưa được cấu hình.");
        }
        try {
            GoogleCredentials credentials = GoogleCredentials.getApplicationDefault();
            if (!(credentials instanceof IdTokenProvider provider)) {
                throw new IllegalStateException(
                        "Application Default Credentials không hỗ trợ Cloud Run ID token.");
            }
            IdTokenCredentials tokenCredentials = IdTokenCredentials.newBuilder()
                    .setIdTokenProvider(provider)
                    .setTargetAudience(audience)
                    .build();
            AccessToken token = tokenCredentials.refreshAccessToken();
            Instant expiresAt = token.getExpirationTime() == null
                    ? Instant.now().plusSeconds(300)
                    : token.getExpirationTime().toInstant();
            return new CachedToken(audience, token.getTokenValue(), expiresAt);
        } catch (IOException exception) {
            throw new IllegalStateException("Không thể lấy Cloud Run ID token cho RAG.", exception);
        }
    }

    private record CachedToken(String audience, String value, Instant expiresAt) {
        boolean valid() {
            return Instant.now().plusSeconds(REFRESH_SKEW_SECONDS).isBefore(expiresAt);
        }
    }
}
