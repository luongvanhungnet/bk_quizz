package com.genquiz.bk.classroom;
import jakarta.validation.constraints.*; import java.time.Instant; import java.util.List; import java.util.UUID;
public final class ClassroomCollaborationDtos { private ClassroomCollaborationDtos(){}
 public record MessageRequest(@Size(max=10000) String content,@Size(max=10) List<UUID> attachmentIds){}
 public record EditMessageRequest(@NotBlank @Size(max=10000) String content){}
 public record AttachmentResponse(UUID id,String name,String mediaType,long sizeBytes,boolean image,String accessUrl){}
 public record MessageResponse(UUID id,UUID classroomId,UUID senderId,String senderUsername,ClassroomMessageType type,
  String content,UUID topicShareId,UUID assignmentId,List<AttachmentResponse> attachments,Instant editedAt,Instant deletedAt,Instant createdAt,long version){}
 public record MessagesPage(List<MessageResponse> items,Instant nextBefore,UUID nextBeforeId,long unreadCount){}
 public record TopicShareRequest(@NotNull UUID topicId,@Size(max=10000) String message){}
 public record TopicShareResponse(UUID id,UUID classroomId,UUID topicId,UUID sharedBy,Instant createdAt){}
 public record AttachmentAccess(String url,Instant expiresAt){}
}
