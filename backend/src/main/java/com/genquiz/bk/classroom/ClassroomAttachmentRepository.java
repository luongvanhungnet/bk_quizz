package com.genquiz.bk.classroom;
import java.util.List; import java.util.Optional; import java.util.UUID; import org.springframework.data.jpa.repository.JpaRepository;
public interface ClassroomAttachmentRepository extends JpaRepository<ClassroomAttachment,UUID>{
 List<ClassroomAttachment> findByMessageId(UUID messageId);
 List<ClassroomAttachment> findByMessageIdIn(java.util.Collection<UUID> messageIds);
 Optional<ClassroomAttachment> findByIdAndClassroomId(UUID id,UUID classroomId);
 List<ClassroomAttachment> findTop100ByMessageIdIsNullAndExpiresAtBeforeOrderByExpiresAt(java.time.Instant now);
}
