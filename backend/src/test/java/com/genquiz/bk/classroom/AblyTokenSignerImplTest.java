package com.genquiz.bk.classroom;

import static org.assertj.core.api.Assertions.assertThat;

import com.genquiz.bk.config.RealtimeProperties;
import io.ably.lib.rest.AblyRest;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class AblyTokenSignerImplTest {
    @Test
    void signsAShortLivedSubscribeOnlyCapabilityForOneClassroom() throws Exception {
        UUID userId = UUID.randomUUID();
        UUID classroomId = UUID.randomUUID();
        RealtimeProperties properties = new RealtimeProperties(
                "ably", "ignored", "bkquiz:classroom:", 300, true);

        try (AblyRest ably = new AblyRest("test-app.test-key:0123456789abcdef0123456789abcdef")) {
            AblyTokenRequest token = new AblyTokenSignerImpl(ably, properties, new ObjectMapper())
                    .createSubscribeToken(userId, classroomId);

            assertThat(token.clientId()).isEqualTo(userId.toString());
            assertThat(token.ttl()).isEqualTo(300_000L);
            assertThat(token.capability())
                    .contains("\"bkquiz:classroom:" + classroomId + "\"")
                    .contains("\"subscribe\"");
            assertThat(token.capability()).doesNotContain("publish");
            assertThat(token.mac()).isNotBlank();
        }
    }
}
