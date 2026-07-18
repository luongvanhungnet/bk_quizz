package com.genquiz.bk.classroom;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity @Table(name = "classroom_messages")
public class ClassroomMessage {
    @Id private UUID id;
    @Column(name="classroom_id", nullable=false, updatable=false) private UUID classroomId;
    @Column(name="sender_id", nullable=false, updatable=false) private UUID senderId;
    @Enumerated(EnumType.STRING) @Column(name="message_type", nullable=false, length=30) private ClassroomMessageType type;
    @Column(columnDefinition="text") private String content;
    @Column(name="topic_share_id") private UUID topicShareId;
    @Column(name="assignment_id") private UUID assignmentId;
    @Column(name="edited_at") private Instant editedAt;
    @Column(name="deleted_at") private Instant deletedAt;
    @Column(name="created_at", nullable=false, updatable=false) private Instant createdAt;
    @Column(name="updated_at", nullable=false) private Instant updatedAt;
    @Version private long version;
    protected ClassroomMessage() {}
    public ClassroomMessage(UUID classroomId, UUID senderId, ClassroomMessageType type, String content,
                            UUID topicShareId, UUID assignmentId, Instant now) {
        this.id=UUID.randomUUID(); this.classroomId=classroomId; this.senderId=senderId; this.type=type;
        this.content=normalize(content); this.topicShareId=topicShareId; this.assignmentId=assignmentId;
        this.createdAt=now; this.updatedAt=now;
    }
    public void edit(String value, Instant now) { content=normalize(value); editedAt=now; updatedAt=now; }
    public void delete(Instant now) { deletedAt=now; content=null; updatedAt=now; }
    private static String normalize(String v){ return v==null||v.isBlank()?null:v.trim(); }
    public UUID getId(){return id;} public UUID getClassroomId(){return classroomId;} public UUID getSenderId(){return senderId;}
    public ClassroomMessageType getType(){return type;} public String getContent(){return content;}
    public UUID getTopicShareId(){return topicShareId;} public UUID getAssignmentId(){return assignmentId;}
    public Instant getEditedAt(){return editedAt;} public Instant getDeletedAt(){return deletedAt;}
    public Instant getCreatedAt(){return createdAt;} public long getVersion(){return version;}
}
