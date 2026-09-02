package com.genquiz.bk.classroom;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "bkquiz.realtime.provider", havingValue = "stomp", matchIfMissing = true)
class StompClassroomRealtimeGateway implements ClassroomRealtimeGateway {
    private final SimpMessagingTemplate messaging;

    StompClassroomRealtimeGateway(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    @Override
    public void publish(ClassroomRealtimeEvent event) {
        messaging.convertAndSend("/topic/classrooms/" + event.classroomId(), event);
    }
}
