package com.genquiz.bk.classroom;

import com.genquiz.bk.common.error.ApiException; import com.genquiz.bk.storage.ClassroomObjectStorage; import com.genquiz.bk.storage.StoredFile; import com.genquiz.bk.storage.StoredFileRepository;
import com.genquiz.bk.topic.*; import com.genquiz.bk.user.*; import java.io.*; import java.time.*; import java.util.*;
import org.springframework.data.domain.PageRequest; import org.springframework.http.HttpStatus; import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional; import org.springframework.web.multipart.MultipartFile;
import org.springframework.context.ApplicationEventPublisher;

@Service
public class ClassroomCollaborationService {
 private final ClassroomRepository classrooms; private final ClassroomMemberRepository members; private final ClassroomMessageRepository messages;
 private final ClassroomAttachmentRepository attachments; private final ClassroomTopicShareRepository shares; private final TopicRepository topics;
 private final UserRepository users; private final ClassroomObjectStorage storage; private final ApplicationEventPublisher events;
 private final StoredFileRepository storedFiles;
 private final ClassroomResourcePresentationService resourcePresentation;
 public ClassroomCollaborationService(ClassroomRepository classrooms,ClassroomMemberRepository members,ClassroomMessageRepository messages,
  ClassroomAttachmentRepository attachments,ClassroomTopicShareRepository shares,TopicRepository topics,UserRepository users,ClassroomObjectStorage storage,ApplicationEventPublisher events,StoredFileRepository storedFiles,ClassroomResourcePresentationService resourcePresentation){
  this.classrooms=classrooms;this.members=members;this.messages=messages;this.attachments=attachments;this.shares=shares;this.topics=topics;this.users=users;this.storage=storage;this.events=events;this.storedFiles=storedFiles;this.resourcePresentation=resourcePresentation;}

 @Transactional(readOnly=true)
 public ClassroomCollaborationDtos.MessagesPage list(UUID actor,UUID classroomId,Instant before,UUID beforeId,int limit){
  if(before!=null&&beforeId==null)throw new ApiException(HttpStatus.BAD_REQUEST,"INVALID_MESSAGE_CURSOR","Cursor tin nhắn không hợp lệ.");
  ClassroomMember member=requireMember(classroomId,actor); PageRequest pageable=PageRequest.of(0,Math.min(limit,100));
  List<ClassroomMessage> values=before==null?messages.findByClassroomIdOrderByCreatedAtDescIdDesc(classroomId,pageable):messages.pageBefore(classroomId,before,beforeId,pageable);
  long unread=messages.countByClassroomIdAndCreatedAtAfter(classroomId,member.getLastReadMessageAt()==null?member.getJoinedAt():member.getLastReadMessageAt());
  ClassroomMessage tail=values.isEmpty()?null:values.get(values.size()-1);
  Map<UUID,ClassroomCollaborationDtos.ResourcePreview> previews=resourcePresentation.previews(values);
  return new ClassroomCollaborationDtos.MessagesPage(values.stream().map(value->response(value,previews.get(value.getId()))).toList(),tail==null?null:tail.getCreatedAt(),tail==null?null:tail.getId(),unread);
 }
 @Transactional
 public ClassroomCollaborationDtos.MessageResponse send(UUID actor,UUID classroomId,ClassroomCollaborationDtos.MessageRequest request){
  requireWritable(classroomId,actor); List<UUID> ids=request.attachmentIds()==null?List.of():request.attachmentIds();
  if((request.content()==null||request.content().isBlank())&&ids.isEmpty()) throw new ApiException(HttpStatus.BAD_REQUEST,"EMPTY_MESSAGE","Tin nhắn không được để trống.");
  List<ClassroomAttachment> files=ids.stream().map(id->attachments.findByIdAndClassroomId(id,classroomId).filter(a->a.getUploaderId().equals(actor)&&a.getMessageId()==null)
   .orElseThrow(()->new ApiException(HttpStatus.BAD_REQUEST,"INVALID_ATTACHMENT","Tệp đính kèm không hợp lệ."))).toList();
  ClassroomMessageType type=files.isEmpty()?ClassroomMessageType.TEXT:files.stream().anyMatch(ClassroomAttachment::isImage)?ClassroomMessageType.IMAGE:ClassroomMessageType.FILE;
  ClassroomMessage message=messages.save(new ClassroomMessage(classroomId,actor,type,request.content(),null,null,Instant.now()));
  files.forEach(file->file.attach(message.getId())); ClassroomCollaborationDtos.MessageResponse result=response(message);
  events.publishEvent(new ClassroomRealtimeEvent(classroomId,"CREATED",result)); return result;
 }
 @Transactional
 public ClassroomCollaborationDtos.MessageResponse edit(UUID actor,UUID classroomId,UUID messageId,String content){
  requireWritable(classroomId,actor); ClassroomMessage message=requireMessage(classroomId,messageId);
  if(!message.getSenderId().equals(actor)) throw forbidden();
  if(message.getCreatedAt().plus(Duration.ofMinutes(15)).isBefore(Instant.now())) throw new ApiException(HttpStatus.CONFLICT,"EDIT_WINDOW_EXPIRED","Đã hết thời gian chỉnh sửa tin nhắn.");
  message.edit(content,Instant.now());ClassroomCollaborationDtos.MessageResponse result=response(message);
  events.publishEvent(new ClassroomRealtimeEvent(classroomId,"UPDATED",result));return result;
 }
 @Transactional public void delete(UUID actor,UUID classroomId,UUID messageId){
  requireMember(classroomId,actor);ClassroomMessage message=requireMessage(classroomId,messageId);
  if(!message.getSenderId().equals(actor)&&!requireMember(classroomId,actor).isTeacher())throw forbidden();message.delete(Instant.now());
  events.publishEvent(new ClassroomRealtimeEvent(classroomId,"DELETED",response(message)));
 }
 @Transactional
 public ClassroomCollaborationDtos.AttachmentResponse upload(UUID actor,UUID classroomId,MultipartFile file) throws IOException{
  requireWritable(classroomId,actor); ClassroomObjectStorage.Stored stored=storage.store(file);String name=safeName(file.getOriginalFilename());
  String relativePath=stored.key().startsWith("local:")?stored.key().substring(6):stored.key();
  StoredFile fileRecord=storedFiles.save(new StoredFile(actor,StoredFile.Purpose.CLASSROOM_ATTACHMENT,stored.provider(),relativePath,name,file.getContentType(),stored.mediaType(),stored.size(),stored.sha256(),false));
  ClassroomAttachment attachment=new ClassroomAttachment(classroomId,actor,stored.key(),name,stored.mediaType(),stored.size(),stored.image(),Instant.now());attachment.attachFile(fileRecord.getId());attachment=attachments.save(attachment);
  return attachment(attachment);
 }
 @Transactional(readOnly=true) public ClassroomAttachment access(UUID actor,UUID classroomId,UUID id){requireMember(classroomId,actor);return attachments.findByIdAndClassroomId(id,classroomId).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"ATTACHMENT_NOT_FOUND","Không tìm thấy tệp."));}
 public InputStream content(ClassroomAttachment attachment){return storage.read(attachment.getObjectKey());}
 public String signedAccess(ClassroomAttachment attachment){return storage.signedGetUrl(attachment.getObjectKey(),Duration.ofMinutes(5));}
 @Transactional public void markRead(UUID actor,UUID classroomId){requireMember(classroomId,actor).markRead(Instant.now());}

 @Transactional
 public ClassroomCollaborationDtos.TopicShareResponse shareTopic(UUID actor,UUID classroomId,ClassroomCollaborationDtos.TopicShareRequest request){
  User sharingUser=users.findById(actor).orElseThrow(this::forbidden);if(!sharingUser.isEmailVerified())throw new ApiException(HttpStatus.FORBIDDEN,"EMAIL_NOT_VERIFIED","Bạn cần xác minh email trước khi chia sẻ nội dung.");
  requireWritable(classroomId,actor);Topic topic=topics.findByIdAndDeletedAtIsNull(request.topicId()).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"TOPIC_NOT_FOUND","Không tìm thấy chủ đề."));
  if(!topic.isOwnedBy(actor)&&!topic.isPubliclyVisible())throw new ApiException(HttpStatus.FORBIDDEN,"TOPIC_SHARE_DENIED","Bạn không có quyền chia sẻ chủ đề này.");
  ClassroomTopicShare share=shares.findByClassroomIdAndTopicIdAndRevokedAtIsNull(classroomId,topic.getId()).orElseGet(()->shares.save(new ClassroomTopicShare(classroomId,topic.getId(),actor,Instant.now())));
  ClassroomMessage message=messages.save(new ClassroomMessage(classroomId,actor,ClassroomMessageType.TOPIC_SHARE,request.message(),share.getId(),null,Instant.now()));
  events.publishEvent(new ClassroomRealtimeEvent(classroomId,"CREATED",response(message)));
  return new ClassroomCollaborationDtos.TopicShareResponse(share.getId(),classroomId,topic.getId(),actor,share.getCreatedAt(),resourcePresentation.topicPreviews(classroomId,List.of(share)).get(share.getId()));
 }
 @Transactional public void revokeTopic(UUID actor,UUID classroomId,UUID shareId){ClassroomTopicShare share=shares.findByIdAndClassroomId(shareId,classroomId).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"SHARE_NOT_FOUND","Không tìm thấy chia sẻ."));
  ClassroomMember member=requireMember(classroomId,actor);if(!share.getSharedBy().equals(actor)&&!member.isTeacher())throw forbidden();share.revoke(Instant.now());}
 @Transactional(readOnly=true) public List<ClassroomCollaborationDtos.TopicShareResponse> topicShares(UUID actor,UUID classroomId){requireMember(classroomId,actor);List<ClassroomTopicShare> values=shares.findByClassroomIdAndRevokedAtIsNullOrderByCreatedAtDesc(classroomId);Map<UUID,ClassroomCollaborationDtos.ResourcePreview> previews=resourcePresentation.topicPreviews(classroomId,values);return values.stream().map(s->new ClassroomCollaborationDtos.TopicShareResponse(s.getId(),s.getClassroomId(),s.getTopicId(),s.getSharedBy(),s.getCreatedAt(),previews.get(s.getId()))).toList();}
 @Transactional(readOnly=true) public ClassroomCollaborationDtos.TopicResourceDetail topicResource(UUID actor,UUID classroomId,UUID shareId){return resourcePresentation.topicDetail(actor,classroomId,shareId);}
 @Transactional(readOnly=true) public ClassroomCollaborationDtos.QuizResourceDetail quizResource(UUID actor,UUID classroomId,UUID assignmentId){return resourcePresentation.quizDetail(actor,classroomId,assignmentId);}

 ClassroomCollaborationDtos.MessageResponse response(ClassroomMessage m){return response(m,resourcePresentation.previews(List.of(m)).get(m.getId()));}
 private ClassroomCollaborationDtos.MessageResponse response(ClassroomMessage m,ClassroomCollaborationDtos.ResourcePreview preview){String username=users.findById(m.getSenderId()).map(User::getUsername).orElse("Người dùng");return new ClassroomCollaborationDtos.MessageResponse(m.getId(),m.getClassroomId(),m.getSenderId(),username,m.getType(),m.getDeletedAt()==null?m.getContent():null,m.getTopicShareId(),m.getAssignmentId(),preview,attachments.findByMessageId(m.getId()).stream().map(this::attachment).toList(),m.getEditedAt(),m.getDeletedAt(),m.getCreatedAt(),m.getVersion());}
 private ClassroomCollaborationDtos.AttachmentResponse attachment(ClassroomAttachment a){return new ClassroomCollaborationDtos.AttachmentResponse(a.getId(),a.getOriginalName(),a.getMediaType(),a.getSizeBytes(),a.isImage(),signedAccess(a));}
 private ClassroomMessage requireMessage(UUID classroomId,UUID id){return messages.findByIdAndClassroomId(id,classroomId).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"MESSAGE_NOT_FOUND","Không tìm thấy tin nhắn."));}
 private ClassroomMember requireMember(UUID classroomId,UUID actor){return members.findByClassroomIdAndUserId(classroomId,actor).filter(ClassroomMember::isActive).orElseThrow(this::forbidden);}
 private Classroom requireWritable(UUID classroomId,UUID actor){requireMember(classroomId,actor);Classroom c=classrooms.findByIdAndDeletedAtIsNull(classroomId).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"CLASSROOM_NOT_FOUND","Không tìm thấy lớp học."));if(c.getStatus()!=ClassroomStatus.ACTIVE)throw new ApiException(HttpStatus.CONFLICT,"CLASSROOM_ARCHIVED","Lớp đã lưu trữ và chỉ có thể đọc.");return c;}
 private ApiException forbidden(){return new ApiException(HttpStatus.FORBIDDEN,"CLASSROOM_ACCESS_DENIED","Bạn không có quyền truy cập lớp học này.");}
 private String safeName(String value){String v=value==null?"file":value.replaceAll("[\\r\\n]"," ");return v.substring(0,Math.min(255,v.length()));}
}
