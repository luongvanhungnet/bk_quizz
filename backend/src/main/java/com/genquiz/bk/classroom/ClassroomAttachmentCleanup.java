package com.genquiz.bk.classroom;

import com.genquiz.bk.storage.ClassroomObjectStorage;
import java.time.Instant;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class ClassroomAttachmentCleanup {
    private final ClassroomAttachmentRepository attachments;
    private final ClassroomObjectStorage storage;
    public ClassroomAttachmentCleanup(ClassroomAttachmentRepository attachments, ClassroomObjectStorage storage) {
        this.attachments = attachments; this.storage = storage;
    }

    @Scheduled(fixedDelayString = "${CLASSROOM_ATTACHMENT_CLEANUP_DELAY:PT1H}")
    @Transactional
    public void cleanupPendingUploads() {
        for (ClassroomAttachment attachment : attachments
                .findTop100ByMessageIdIsNullAndExpiresAtBeforeOrderByExpiresAt(Instant.now())) {
            storage.delete(attachment.getObjectKey());
            attachments.delete(attachment);
        }
    }
}
