package com.genquiz.bk.classroom;

import com.genquiz.bk.config.RealtimeProperties;
import io.ably.lib.rest.AblyRest;
import io.ably.lib.types.AblyException;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Component
@ConditionalOnProperty(name = "bkquiz.realtime.provider", havingValue = "ably")
class AblyClassroomRealtimeGateway implements ClassroomRealtimeGateway {
    private static final String EVENT_NAME = "classroom-event";
    private final AblyRest ably;
    private final RealtimeProperties properties;
    private final ObjectMapper objectMapper;

    AblyClassroomRealtimeGateway(AblyRest ably, RealtimeProperties properties, ObjectMapper objectMapper) {
        this.ably = ably;
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    @Override
    public void publish(ClassroomRealtimeEvent event) {
        if (!properties.publishEnabled()) return;
        try {
            String payload = objectMapper.writeValueAsString(event);
            ably.channels.get(properties.classroomChannel(event.classroomId())).publish(EVENT_NAME, payload);
        } catch (AblyException | JacksonException exception) {
            throw new RealtimeUnavailableException("Không thể phát sự kiện realtime.", exception);
        }
    }
}
