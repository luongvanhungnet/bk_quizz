package com.genquiz.bk.classroom;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ClassroomRealtimePublisher {
    private static final Logger log = LoggerFactory.getLogger(ClassroomRealtimePublisher.class);
    private final ClassroomRealtimeGateway gateway;
    public ClassroomRealtimePublisher(ClassroomRealtimeGateway gateway) { this.gateway = gateway; }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void publish(ClassroomRealtimeEvent event) {
        try {
            gateway.publish(event);
        } catch (RealtimeUnavailableException exception) {
            log.warn("Realtime publish failed classroomId={} action={} type={}",
                    event.classroomId(), event.action(), exception.getClass().getSimpleName());
        }
    }
}
