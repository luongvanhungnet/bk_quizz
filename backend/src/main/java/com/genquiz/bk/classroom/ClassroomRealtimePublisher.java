package com.genquiz.bk.classroom;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ClassroomRealtimePublisher {
    private final SimpMessagingTemplate messaging;
    public ClassroomRealtimePublisher(SimpMessagingTemplate messaging) { this.messaging = messaging; }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void publish(ClassroomRealtimeEvent event) {
        messaging.convertAndSend("/topic/classrooms/" + event.classroomId(), event);
    }
}
