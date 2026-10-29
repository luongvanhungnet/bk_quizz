package com.genquiz.bk.abuse;

import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;

@Component
public class TurnstileChallengeVerifier implements ChallengeVerifier {
    private final AntiAbuseProperties properties;
    private final RestClient client;

    public TurnstileChallengeVerifier(AntiAbuseProperties properties, RestClient.Builder builder) {
        this.properties = properties;
        this.client = builder.build();
    }

    @Override
    public boolean verify(String token, String ignoredIpHash) {
        if (!properties.turnstile().enabled() || token == null || token.isBlank()
                || properties.turnstile().secretKey() == null || properties.turnstile().secretKey().isBlank()) {
            return false;
        }
        try {
            var form = new LinkedMultiValueMap<String, String>();
            form.add("secret", properties.turnstile().secretKey());
            form.add("response", token);
            Map<?, ?> response = client.post().uri(properties.turnstile().verifyUrl())
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED).body(form)
                    .retrieve().body(Map.class);
            return response != null && Boolean.TRUE.equals(response.get("success"));
        } catch (RuntimeException exception) {
            return false;
        }
    }
}
