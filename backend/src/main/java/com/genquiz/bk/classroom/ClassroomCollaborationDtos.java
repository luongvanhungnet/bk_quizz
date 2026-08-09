package com.genquiz.bk.classroom;
import com.genquiz.bk.quiz.Difficulty; import com.genquiz.bk.quiz.CognitiveMode;
import com.genquiz.bk.quiz.QuizDtos;
import com.genquiz.bk.topic.TopicDtos;
import jakarta.validation.constraints.*; import java.time.Instant; import java.util.List; import java.util.UUID;
public final class ClassroomCollaborationDtos { private ClassroomCollaborationDtos(){}
 public record MessageRequest(@Size(max=10000) String content,@Size(max=10) List<UUID> attachmentIds){}
 public record EditMessageRequest(@NotBlank @Size(max=10000) String content){}
 public record AttachmentResponse(UUID id,String name,String mediaType,long sizeBytes,boolean image,String accessUrl){}
 public record ResourcePreview(String kind,UUID resourceId,UUID referenceId,String title,String description,
  String ownerUsername,boolean available,String unavailableReason,long quizCount,long questionCount,
  Difficulty difficulty,CognitiveMode cognitiveMode,Integer durationMinutes,AssignmentStatus assignmentStatus,Instant opensAt,
  Instant dueAt,Integer maxAttempts){}
 public record MessageResponse(UUID id,UUID classroomId,UUID senderId,String senderUsername,ClassroomMessageType type,
  String content,UUID topicShareId,UUID assignmentId,ResourcePreview resourcePreview,
  List<AttachmentResponse> attachments,Instant editedAt,Instant deletedAt,Instant createdAt,long version){}
 public record MessagesPage(List<MessageResponse> items,Instant nextBefore,UUID nextBeforeId,long unreadCount){}
 public record TopicShareRequest(@NotNull UUID topicId,@Size(max=10000) String message){}
 public record TopicShareResponse(UUID id,UUID classroomId,UUID topicId,UUID sharedBy,Instant createdAt,
  ResourcePreview resourcePreview){}
 public record TopicResourceDetail(ResourcePreview preview,TopicDtos.Response topic,
  List<QuizDtos.QuizResponse> quizzes){}
 public record QuizResourceDetail(ResourcePreview preview,QuizDtos.QuizResponse quiz,
  ClassroomDtos.AssignmentResponse assignment){}
 public record AttachmentAccess(String url,Instant expiresAt){}
}
