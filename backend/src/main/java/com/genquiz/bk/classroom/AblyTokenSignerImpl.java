package com.genquiz.bk.classroom;

import com.genquiz.bk.config.RealtimeProperties;
import io.ably.lib.rest.AblyRest;
import io.ably.lib.rest.Auth;
import io.ably.lib.types.AblyException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Component
@ConditionalOnProperty(name = "bkquiz.realtime.provider", havingValue = "ably")
class AblyTokenSignerImpl implements AblyTokenSigner {
    private final AblyRest ably;
    private final RealtimeProperties properties;
    private final ObjectMapper objectMapper;

    AblyTokenSignerImpl(AblyRest ably, RealtimeProperties properties, ObjectMapper objectMapper) {
        this.ably = ably;
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    @Override
    public AblyTokenRequest createSubscribeToken(UUID userId, UUID classroomId) {
        Auth.TokenParams params = new Auth.TokenParams();
        params.clientId = userId.toString();
        params.ttl = properties.tokenTtl().toMillis();
        params.capability = capability(properties.classroomChannel(classroomId));
        try {
            Auth.TokenRequest request = ably.auth.createTokenRequest(params, null);
            return new AblyTokenRequest(request.keyName, request.ttl, request.capability,
                    request.clientId, request.timestamp, request.nonce, request.mac);
        } catch (AblyException exception) {
            throw new RealtimeUnavailableException("Không thể cấp quyền kết nối realtime.", exception);
        }
    }

    private String capability(String channel) {
        try {
            return objectMapper.writeValueAsString(Map.of(channel, List.of("subscribe")));
        } catch (JacksonException exception) {
            throw new IllegalStateException("Cannot serialize Ably capability.", exception);
        }
    }
}
